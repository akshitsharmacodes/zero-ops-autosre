"""In-memory stand-ins for database connections so tests never need a database server."""

CANNED_ROWS = {
    "GROUP BY user_id": [(101, 7, "2026-10-20 10:00:00"), (102, 3, "2026-10-20 09:30:00")],
    "GROUP BY page": [("/home", 42), ("/pricing", 17)],
}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False
        self._rows = []

    def execute(self, sql, params=None):
        if self.closed or self.conn.closed:
            raise RuntimeError("cursor used after close")
        self.conn.queries.append(sql)
        self._rows = next((rows for key, rows in CANNED_ROWS.items() if key in sql), [])

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeConnection:
    def __init__(self):
        self.closed = 0
        self.queries = []
        self.rollbacks = 0

    def cursor(self):
        if self.closed:
            raise RuntimeError("connection already closed")
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        pass

    def close(self):
        self.closed = 1
