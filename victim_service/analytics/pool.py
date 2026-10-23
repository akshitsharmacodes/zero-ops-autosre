"""
Reporting connection pool.

Raw-SQL reports bypass the ORM for speed. Opening a database connection is slow, so
report connections are pooled: acquire() hands out a free connection (or opens a new
one) and release() rolls back any open transaction and puts it back.

Always use the context manager so the connection is returned even on errors:

    with report_pool.connection() as conn:
        cursor = conn.cursor()
        ...
"""
import logging
import threading
from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger("analytics.pool")

APPLICATION_NAME = "victim-service:reports"


def _connect_default():
    db = settings.DATABASES["default"]
    if db["ENGINE"].endswith("postgresql"):
        import psycopg2

        return psycopg2.connect(
            host=db["HOST"],
            port=db["PORT"],
            dbname=db["NAME"],
            user=db["USER"],
            password=db["PASSWORD"],
            application_name=APPLICATION_NAME,
            connect_timeout=5,
        )
    import sqlite3

    return sqlite3.connect(str(db["NAME"]), check_same_thread=False)


class ReportConnectionPool:
    def __init__(self, connect=None):
        self._connect = connect or _connect_default
        self._lock = threading.Lock()
        self._free = []
        self._in_use = []
        self.opened = 0

    def acquire(self):
        with self._lock:
            while self._free:
                conn = self._free.pop()
                if not getattr(conn, "closed", False):
                    self._in_use.append(conn)
                    return conn
        conn = self._connect()
        with self._lock:
            self.opened += 1
            self._in_use.append(conn)
            in_use = len(self._in_use)
        logger.info("opened report connection", extra={"pool_in_use": in_use, "pool_opened": self.opened})
        if in_use >= 20 and in_use % 10 == 0:
            logger.warning("report pool has %d connections checked out", in_use, extra={"pool_in_use": in_use})
        return conn

    def release(self, conn):
        try:
            conn.rollback()
            healthy = not getattr(conn, "closed", False)
        except Exception:
            healthy = False
        with self._lock:
            if conn in self._in_use:
                self._in_use.remove(conn)
            if healthy:
                self._free.append(conn)
        if not healthy:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def connection(self):
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)

    def stats(self):
        with self._lock:
            return {"in_use": len(self._in_use), "free": len(self._free), "opened": self.opened}

    def reset(self, connect=None):
        """Close everything and start fresh (used by tests)."""
        with self._lock:
            conns, self._free, self._in_use = self._free + self._in_use, [], []
            self.opened = 0
            self._connect = connect or _connect_default
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass


report_pool = ReportConnectionPool()
