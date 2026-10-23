"""
Real PostgreSQL + real victim service (TC-2 and acceptance criteria 1 & 7).

Runs only when the demo stack is up:   docker compose up -d --build
Skipped automatically otherwise.
"""
import time
import urllib.request

import pytest
from django.conf import settings

from telemetry import TelemetryUnavailable, get_adapter

pytestmark = pytest.mark.postgres


def _stack_up() -> bool:
    try:
        get_adapter().snapshot()
        with urllib.request.urlopen(settings.TARGET_APP["BASE_URL"] + "/api/health/", timeout=3) as r:
            return r.status == 200
    except (TelemetryUnavailable, OSError):
        return False


pytestmark = [pytestmark, pytest.mark.skipif(not _stack_up(), reason="demo stack not running (docker compose up -d)")]


def _hit(path, n):
    codes = []
    for _ in range(n):
        try:
            with urllib.request.urlopen(settings.TARGET_APP["BASE_URL"] + path, timeout=10) as r:
                codes.append(r.status)
        except urllib.error.HTTPError as exc:
            codes.append(exc.code)
    return codes


def test_leak_is_real_and_mitigation_restores_capacity_tc2():
    adapter = get_adapter()
    prefix = settings.TARGET_DB["APP_NAME_PREFIX"]
    # clean slate
    adapter.terminate([s.pid for s in adapter.stuck_sessions(0, prefix)], prefix, 0)
    before = adapter.snapshot()

    # The healthy endpoint does not leak...
    _hit("/api/reports/top-pages/", 20)
    time.sleep(1)
    assert len(adapter.stuck_sessions(0, prefix)) <= 2  # one pooled connection per worker, released

    # ...the leaky one does: every request strands a session idle in transaction.
    _hit("/api/reports/user-activity/", 30)
    time.sleep(1)
    stuck = adapter.stuck_sessions(0, prefix)
    assert len(stuck) >= 25
    assert all(s.application_name == "victim-service:reports" for s in stuck)
    assert "analytics_useractivity" in stuck[0].query

    # Stop the bleeding ends exactly those sessions.
    ended = adapter.terminate([s.pid for s in stuck], prefix, 0)
    assert len(ended) == len(stuck)
    time.sleep(0.5)
    assert adapter.snapshot().idle_in_transaction <= before.idle_in_transaction + 1


def test_autosre_role_cannot_touch_other_apps():
    adapter = get_adapter()
    with pytest.raises(ValueError):
        adapter.terminate([1], "", 0)  # refuses without an application filter
