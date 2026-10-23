"""Test doubles shared across backend tests."""
from telemetry import ConnectionSnapshot, DatabaseAdapter, SessionInfo, TelemetryUnavailable

LEAK_QUERY = (
    "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
    "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
)


class FakeAdapter(DatabaseAdapter):
    """Pretends to be a saturated PostgreSQL with a leaking app."""

    engine = "fake"

    def __init__(self, leaked=88, healthy_idle=6, max_connections=100, reachable=True):
        self.reachable = reachable
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

    def _check(self):
        if not self.reachable:
            raise TelemetryUnavailable("fake database is down")

    def snapshot(self):
        self._check()
        return ConnectionSnapshot(
            active=2, idle=self.healthy_idle, idle_in_transaction=len(self.sessions), other=0,
            max_connections=self.max_connections,
            by_application={"victim-service:reports": len(self.sessions) - 1, "psql": 1},
        )

    def stuck_sessions(self, min_idle_seconds, app_prefix=None):
        self._check()
        return [s for s in self.sessions
                if s.state_age_seconds >= min_idle_seconds
                and (app_prefix is None or s.application_name.startswith(app_prefix))]

    def terminate(self, pids, app_prefix, min_idle_seconds):
        self._check()
        allowed = {s.pid for s in self.stuck_sessions(min_idle_seconds, app_prefix)}
        done = [p for p in pids if p in allowed]
        self.terminated.extend(done)
        self.sessions = [s for s in self.sessions if s.pid not in done]
        return done
