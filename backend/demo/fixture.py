"""
In-memory database and a canned log for the prototype.

Play prototype does not need PostgreSQL or the victim container. The numbers and the
log lines are the same shape the live incident produces, so diagnosis and correlation
still run.
"""
from __future__ import annotations

import json
from pathlib import Path

from telemetry import ConnectionSnapshot, DatabaseAdapter, SessionInfo

LEAK_QUERY = (
    "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
    "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
)

LOG_LINES = [
    {"level": "INFO", "logger": "victim.request", "msg": "request", "path": "/api/reports/user-activity/",
     "status": 200, "view": "analytics.views.user_activity_report"},
    {"level": "WARNING", "logger": "analytics.pool", "msg": "report pool has 40 connections checked out"},
    {"level": "ERROR", "logger": "django.request", "msg": "Internal Server Error: /api/reports/user-activity/",
     "path": "/api/reports/user-activity/", "status": 500,
     "exc": 'File "/app/analytics/views.py", line 34, in user_activity_report\n'
            "psycopg2.OperationalError: FATAL: sorry, too many clients already"},
]


class FixtureAdapter(DatabaseAdapter):
    """98 of 100 connections, with the victim app holding leaked sessions."""

    engine = "fixture"

    def __init__(self, leaked: int = 89, healthy_idle: int = 6, max_connections: int = 100):
        self.max_connections = max_connections
        self.healthy_idle = healthy_idle
        self.sessions = [
            SessionInfo(pid=1000 + i, application_name="victim-service:reports", user="victim_app",
                        state="idle in transaction", state_age_seconds=30.0 + i, xact_age_seconds=31.0 + i,
                        query=LEAK_QUERY)
            for i in range(leaked)
        ]
        self.sessions.append(
            SessionInfo(pid=999, application_name="psql", user="dba", state="idle in transaction",
                        state_age_seconds=40.0, xact_age_seconds=40.0, query="BEGIN")
        )
        self.terminated: list[int] = []

    def snapshot(self) -> ConnectionSnapshot:
        return ConnectionSnapshot(
            active=2, idle=self.healthy_idle, idle_in_transaction=len(self.sessions), other=0,
            max_connections=self.max_connections,
            by_application={"victim-service:reports": len(self.sessions) - 1, "psql": 1},
        )

    def stuck_sessions(self, min_idle_seconds: int, app_prefix: str | None = None) -> list[SessionInfo]:
        return [s for s in self.sessions
                if s.state_age_seconds >= min_idle_seconds
                and (app_prefix is None or s.application_name.startswith(app_prefix))]

    def terminate(self, pids: list[int], app_prefix: str, min_idle_seconds: int) -> list[int]:
        allowed = {s.pid for s in self.stuck_sessions(min_idle_seconds, app_prefix)}
        done = [p for p in pids if p in allowed]
        self.terminated.extend(done)
        self.sessions = [s for s in self.sessions if s.pid not in done]
        return done


def prototype_log_path() -> Path:
    from django.conf import settings

    path = Path(settings.VAR_DIR) / "logs" / "prototype.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in LOG_LINES) + "\n", encoding="utf-8")
    return path
