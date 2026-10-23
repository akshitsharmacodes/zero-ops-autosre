"""PostgreSQL adapter (reads pg_stat_activity; uses pg_terminate_backend for mitigation)."""
from __future__ import annotations

import logging

import psycopg2

from .base import ConnectionSnapshot, DatabaseAdapter, SessionInfo, TelemetryUnavailable

logger = logging.getLogger("autosre.telemetry.postgres")

SNAPSHOT_SQL = """
    SELECT
        count(*) FILTER (WHERE state = 'active')                         AS active,
        count(*) FILTER (WHERE state = 'idle')                           AS idle,
        count(*) FILTER (WHERE state IN ('idle in transaction',
                                         'idle in transaction (aborted)')) AS idle_in_tx,
        count(*) FILTER (WHERE state IS NULL OR state NOT IN (
            'active', 'idle', 'idle in transaction',
            'idle in transaction (aborted)'))                            AS other,
        current_setting('max_connections')::int                         AS max_conn
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
"""

BY_APP_SQL = """
    SELECT coalesce(nullif(application_name, ''), '(unnamed)') AS app, count(*)
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 20
"""

STUCK_SQL = """
    SELECT pid, application_name, usename, state,
           extract(epoch FROM now() - state_change)  AS state_age,
           extract(epoch FROM now() - xact_start)    AS xact_age,
           query
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
      AND state IN ('idle in transaction', 'idle in transaction (aborted)')
      AND now() - state_change >= make_interval(secs => %(min_idle)s)
      AND (%(prefix)s::text IS NULL OR application_name LIKE %(prefix)s || '%%')
    ORDER BY state_change ASC
    LIMIT 500
"""

# Re-checks every condition at the moment of termination, so we can only ever end
# sessions that belong to the application AND are still stuck (NFR-F4).
TERMINATE_SQL = """
    SELECT pid, pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE pid = ANY(%(pids)s)
      AND backend_type = 'client backend'
      AND application_name LIKE %(prefix)s || '%%'
      AND state IN ('idle in transaction', 'idle in transaction (aborted)')
      AND now() - state_change >= make_interval(secs => %(min_idle)s)
      AND pid <> pg_backend_pid()
"""


class PostgresAdapter(DatabaseAdapter):
    engine = "postgres"

    def __init__(self, host: str, port: int, dbname: str, user: str, password: str, connect_timeout: int = 3):
        self._params = dict(
            host=host, port=port, dbname=dbname, user=user, password=password,
            connect_timeout=connect_timeout, application_name="autosre-agent",
            options="-c statement_timeout=5000",
        )

    def _query(self, sql: str, params: dict | None = None) -> list[tuple]:
        try:
            conn = psycopg2.connect(**self._params)
        except psycopg2.Error as exc:
            raise TelemetryUnavailable(f"cannot connect to PostgreSQL at {self._params['host']}:{self._params['port']}: {str(exc).strip()}") from exc
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                return cur.fetchall()
        except psycopg2.Error as exc:
            raise TelemetryUnavailable(f"PostgreSQL query failed: {str(exc).strip()}") from exc
        finally:
            conn.close()

    def snapshot(self) -> ConnectionSnapshot:
        active, idle, idle_in_tx, other, max_conn = self._query(SNAPSHOT_SQL)[0]
        by_app = {app: n for app, n in self._query(BY_APP_SQL)}
        return ConnectionSnapshot(
            active=active, idle=idle, idle_in_transaction=idle_in_tx, other=other,
            max_connections=max_conn, by_application=by_app,
        )

    def stuck_sessions(self, min_idle_seconds: int, app_prefix: str | None = None) -> list[SessionInfo]:
        rows = self._query(STUCK_SQL, {"min_idle": min_idle_seconds, "prefix": app_prefix})
        return [
            SessionInfo(
                pid=pid, application_name=app or "", user=user or "", state=state,
                state_age_seconds=round(float(state_age or 0), 1),
                xact_age_seconds=round(float(xact_age), 1) if xact_age is not None else None,
                query=(query or "").strip(),
            )
            for pid, app, user, state, state_age, xact_age, query in rows
        ]

    def terminate(self, pids: list[int], app_prefix: str, min_idle_seconds: int) -> list[int]:
        if not pids:
            return []
        if not app_prefix:
            raise ValueError("refusing to terminate sessions without an application filter")
        rows = self._query(TERMINATE_SQL, {"pids": list(pids), "prefix": app_prefix, "min_idle": min_idle_seconds})
        return [pid for pid, ok in rows if ok]

    def describe(self) -> dict:
        version = self._query("SHOW server_version")[0][0]
        return {"engine": self.engine, "version": version, "host": self._params["host"], "database": self._params["dbname"]}
