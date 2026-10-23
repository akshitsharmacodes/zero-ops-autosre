"""Phase 2: alert ingestion, monitor, log parsing, diagnosis and stop-the-bleeding."""
import json

import pytest
from django.test import Client

from diagnostics.diagnosis import build_diagnosis, normalize_query
from diagnostics.logs import parse_lines, summarize_log_file
from diagnostics.mitigation import stop_the_bleeding
from incidents.models import Incident, TelemetrySample, TimelineEvent
from incidents.monitor import AlertMonitor
from incidents.services import ingest_alert

from .fakes import LEAK_QUERY, FakeAdapter

SRS_ALERT = {"source": "pg-monitor", "severity": "critical", "metric": "pg_connections",
             "value": 98, "max": 100, "timestamp": "2026-10-17T03:12:00Z"}

LOG_LINES = [
    json.dumps({"level": "INFO", "logger": "victim.request", "msg": "request", "method": "GET",
                "path": "/api/reports/user-activity/", "status": 200,
                "view": "analytics.views.user_activity_report"}),
    json.dumps({"level": "WARNING", "logger": "analytics.pool", "msg": "report pool has 40 connections checked out"}),
    json.dumps({"level": "ERROR", "logger": "django.request",
                "msg": "Internal Server Error: /api/reports/user-activity/", "path": "/api/reports/user-activity/",
                "status": 500,
                "exc": 'Traceback (most recent call last):\n'
                       '  File "/usr/local/lib/python3.11/site-packages/django/core/handlers/base.py", line 197, in _get_response\n'
                       '  File "/app/analytics/views.py", line 34, in user_activity_report\n'
                       '  File "/app/analytics/pool.py", line 59, in acquire\n'
                       'psycopg2.OperationalError: FATAL:  sorry, too many clients already'}),
    "plain text line: connection refused by upstream",
]


# --- TC-1 / TC-12: alert ingestion and duplicate suppression ------------------

@pytest.mark.django_db
def test_webhook_creates_incident_tc1():
    resp = Client().post("/api/v1/alerts", SRS_ALERT, content_type="application/json")
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["created"] is True
    inc = Incident.objects.get(pk=body["incident"]["id"])
    assert inc.alert["value"] == 98 and inc.status == "ALERT_RECEIVED"


@pytest.mark.django_db
def test_duplicate_alert_is_ignored_tc12():
    first, created = ingest_alert(SRS_ALERT, start=False)
    second, created_again = ingest_alert(SRS_ALERT, start=False)
    assert created and not created_again
    assert first.pk == second.pk
    assert Incident.objects.count() == 1
    assert TimelineEvent.objects.filter(incident=first, message__startswith="Duplicate alert").exists()


@pytest.mark.django_db
def test_new_incident_after_previous_is_final():
    first, _ = ingest_alert(SRS_ALERT, start=False)
    Incident.objects.filter(pk=first.pk).update(status="ESCALATED")
    second, created = ingest_alert(SRS_ALERT, start=False)
    assert created and second.pk != first.pk


# --- Monitor --------------------------------------------------------------------

@pytest.mark.django_db
def test_monitor_samples_and_raises_one_alert():
    monitor = AlertMonitor(adapter=FakeAdapter(leaked=90), interval=0.01, start_incidents=False)
    monitor.tick()
    monitor.tick()
    assert TelemetrySample.objects.count() == 2
    assert Incident.objects.count() == 1
    assert Incident.objects.get().source == "monitor"


@pytest.mark.django_db
def test_monitor_below_threshold_does_not_alert():
    AlertMonitor(adapter=FakeAdapter(leaked=10), start_incidents=False).tick()
    assert Incident.objects.count() == 0


@pytest.mark.django_db
def test_monitor_survives_unreachable_database():
    monitor = AlertMonitor(adapter=FakeAdapter(reachable=False), start_incidents=False)
    assert monitor.tick() is None
    assert "down" in monitor.last_error
    assert TelemetrySample.objects.count() == 0


# --- Logs + diagnosis ---------------------------------------------------------------

def test_log_parser_extracts_errors_paths_and_app_frames():
    summary = parse_lines(LOG_LINES)
    assert summary.errors["connection_exhaustion"] == 1
    assert summary.errors["connect_failure"] == 1
    assert summary.failing_paths == [("/api/reports/user-activity/", 1)]
    assert ("analytics.pool", 1) in summary.warning_loggers
    files = [f["file"] for f in summary.frames]
    assert "/app/analytics/views.py" in files
    assert not any("site-packages" in f for f in files)


def test_missing_log_file_is_reported_honestly(tmp_path):
    summary = summarize_log_file(tmp_path / "nope.log")
    assert summary.readable is False and summary.note


def test_diagnosis_groups_leak_and_computes_delta():
    adapter = FakeAdapter(leaked=88)
    diagnosis = build_diagnosis(
        adapter.snapshot(), adapter.stuck_sessions(5), parse_lines(LOG_LINES),
        baseline={"total": 10, "active": 2, "idle": 8, "idle_in_transaction": 0},
    )
    top = diagnosis["stuck_sessions"]["groups"][0]
    assert top["application_name"] == "victim-service:reports" and top["count"] == 88
    assert diagnosis["leak_suspected"] is True
    assert diagnosis["delta"]["idle_in_transaction"] == 89
    assert diagnosis["evidence"]["queries"][0] == LEAK_QUERY
    assert "/api/reports/user-activity/" in diagnosis["evidence"]["endpoints"]


def test_normalize_query_groups_literals():
    assert normalize_query("SELECT  1 FROM t WHERE id = 42 AND name='x'") == "SELECT ? FROM t WHERE id = ? AND name=?"


# --- Stop the bleeding ------------------------------------------------------------------

def test_stop_the_bleeding_only_touches_the_app():
    adapter = FakeAdapter(leaked=88)
    stuck = adapter.stuck_sessions(5)
    result = stop_the_bleeding(adapter, stuck, app_prefix="victim-service", min_idle_seconds=5)
    assert result["terminated"] == 88
    assert result["skipped_other_apps"] == 1
    assert 999 not in adapter.terminated  # the DBA's psql session survives
    assert result["after"]["idle_in_transaction"] == 1
