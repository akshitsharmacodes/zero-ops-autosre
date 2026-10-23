"""
Demo controls (FR-8.5, NFR-U2). These simulate the outside world — traffic, a teammate,
a human reviewer — they never let AutoSRE itself skip a safety rule.
"""
from __future__ import annotations

import sys

from django.conf import settings
from rest_framework.decorators import api_view

from delivery.providers import DeliveryError, LocalProvider, get_provider
from demo.teammate import push_teammate_change
from demo.traffic import driver, victim_reachable
from telemetry import TelemetryUnavailable, get_adapter

from ..models import Incident, RunMode, TelemetrySample, TimelineEvent
from ..replay import recording_available
from ..services import ingest_alert
from .envelope import fail, ok
from .serializers import IncidentSummarySerializer


@api_view(["POST"])
def prototype(request):
    """One-click story: fixture database, cached checks, then a real conflicting commit."""
    incident, created = ingest_alert(
        {"source": "prototype", "metric": "pg_connections", "value": 98, "max": 100,
         "severity": "critical", "service": settings.TARGET_DB["NAME"]},
        source="prototype", mode=RunMode.CACHED, approval_mode="autonomous",
    )
    if not created:
        return fail("ALREADY_RUNNING", f"{incident.id} is already open. Reset it before playing the prototype again.", 409)
    incident.refresh_from_db()
    return ok({
        "incident": IncidentSummarySerializer(incident).data,
        "message": "Prototype started. After the pull request is ready, a teammate commit lands on main.",
    }, status=201)


@api_view(["POST"])
def trigger(request):
    """Start realistic HTTP traffic. The victim leaks; the monitor opens the incident by itself."""
    base_url = settings.TARGET_APP["BASE_URL"]
    if not victim_reachable(base_url):
        return fail("VICTIM_UNREACHABLE", f"victim service is not reachable at {base_url} (docker compose up -d)", 503)
    body = request.data or {}
    status = driver.start(base_url, total=int(body.get("requests", 400)), concurrency=int(body.get("concurrency", 8)))
    return ok({"traffic": status, "message": "Traffic started. The Alert Monitor will open an incident when "
                                             f"connections pass {int(settings.AUTOSRE['ALERT_THRESHOLD'] * 100)}%."})


@api_view(["GET"])
def traffic_status(request):
    return ok(driver.status())


@api_view(["POST"])
def replay(request):
    if not recording_available():
        return fail("NO_RECORDING", "no recorded run yet: finish one live/cached run, then "
                                    "`python manage.py export_replay <incident_id>`", 409)
    incident, created = ingest_alert({"source": "replay", "metric": "pg_connections_replay", "value": 98, "max": 100},
                                     source="replay", start=False)
    if not created:
        return fail("ALREADY_RUNNING", f"replay {incident.id} is already running", 409)
    Incident.objects.filter(pk=incident.pk).update(mode=RunMode.REPLAY)
    from django.db import transaction

    from ..runner import launch

    transaction.on_commit(lambda: launch(incident.id))
    incident.refresh_from_db()
    return ok({"incident": IncidentSummarySerializer(incident).data}, status=201)


@api_view(["POST"])
def teammate_push(request):
    """Simulate a teammate pushing a conflicting change to main (local provider only)."""
    try:
        sha = push_teammate_change(get_provider())
    except DeliveryError as exc:
        return fail("NOT_AVAILABLE", str(exc), 409)
    for inc in Incident.objects.filter(status__in=["PR_CREATED", "READY_TO_MERGE", "UPDATING_PR"]):
        TimelineEvent.objects.create(incident=inc, tag="LOOP", state=inc.status,
                                     message=f"A teammate pushed {sha[:8]} to main (raises the report LIMIT to 100).")
    return ok({"sha": sha})


@api_view(["POST"])
def human_merge(request, incident_id):
    """The human reviewer's 'Merge' button for the local provider. AutoSRE never merges on its own."""
    inc = Incident.objects.filter(pk=incident_id).first()
    if not inc or not inc.pull_request.get("number"):
        return fail("NOT_FOUND", "incident has no pull request", 404)
    provider = get_provider()
    if not isinstance(provider, LocalProvider):
        return fail("NOT_AVAILABLE", "merge real GitHub pull requests on GitHub", 409)
    try:
        sha = provider.human_merge(int(inc.pull_request["number"]))
    except DeliveryError as exc:
        return fail("CANNOT_MERGE", str(exc), 409)
    return ok({"merged": True, "sha": sha})


@api_view(["POST"])
def reset(request):
    """Stop traffic and end the victim's leaked sessions. Optionally clear incidents and re-seed the repo."""
    body = request.data or {}
    driver.stop()
    result = {"traffic_stopped": True}
    try:
        adapter = get_adapter()
        prefix = settings.TARGET_DB["APP_NAME_PREFIX"]
        stuck = adapter.stuck_sessions(0, prefix)
        result["sessions_ended"] = len(adapter.terminate([s.pid for s in stuck], prefix, 0))
    except TelemetryUnavailable as exc:
        result["sessions_ended"] = 0
        result["database_error"] = str(exc)
    if body.get("clear_incidents"):
        active = Incident.objects.filter(status__in=["DIAGNOSING", "MITIGATING", "CORRELATING", "PATCHING",
                                                     "TESTING_IN_SANDBOX", "UPDATING_PR"]).exists()
        if active:
            return fail("BUSY", "an incident is still being worked on; wait for it to finish", 409)
        result["incidents_deleted"] = Incident.objects.all().delete()[0]
        TelemetrySample.objects.all().delete()
    if body.get("reseed_repo"):
        if str(settings.REPO_ROOT / "scripts") not in sys.path:
            sys.path.append(str(settings.REPO_ROOT / "scripts"))  # never shadow backend packages
        from seed_victim_repo import seed

        seed(settings.VAR_DIR, force=True)
        result["repo_reseeded"] = True
    return ok(result)
