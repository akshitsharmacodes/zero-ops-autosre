"""
Recorded agent decisions for cached mode (FR-9.1): the demo works with no Wi-Fi or API key.

Only the *decisions* are recorded. Every tool still runs for real: files are really
edited, guardrails really checked, the sandbox really runs the tests. That is why the
first attempt genuinely fails and the retry genuinely passes.

The fix recording mirrors a mistake real models often make: calling release() after
`return` (it never runs), then correcting it to a context manager once the failing
test output shows the connection is still leaked.
"""
from __future__ import annotations

from .llm import ScriptedClient

VICTIM_FILE = "analytics/views.py"
REGRESSION_TEST_PATH = "tests/test_user_activity_releases_connection.py"

REGRESSION_TEST = '''from django.test import Client


def test_user_activity_report_returns_connection_to_pool(fake_report_pool):
    """Regression test for the incident: every request must give its pooled connection back."""
    client = Client()
    for _ in range(5):
        assert client.get("/api/reports/user-activity/").status_code == 200
    stats = fake_report_pool.stats()
    assert stats["in_use"] == 0, f"{stats['in_use']} report connection(s) were never returned to the pool"
    assert stats["opened"] == 1
'''

RETURN_LINE = '    return JsonResponse({"status": "success", "count": len(data), "data": data})'

FLAWED_FIX = RETURN_LINE + "\n    report_pool.release(conn)"

LEAKY_BODY = '''    conn = report_pool.acquire()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
        "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
    )
    rows = cursor.fetchall()
    data = [{"user_id": r[0], "events": r[1], "last_seen": str(r[2])} for r in rows]
'''

FIXED_BODY = '''    with report_pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
            "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
        )
        rows = cursor.fetchall()
    data = [{"user_id": r[0], "events": r[1], "last_seen": str(r[2])} for r in rows]
'''


def fix_recording() -> ScriptedClient:
    return ScriptedClient([
        ("Start with the suspect function the correlation pointed at.",
         "read_file", {"path": VICTIM_FILE}),
        ("It calls report_pool.acquire() but never gives the connection back. Check the pool API.",
         "read_file", {"path": "analytics/pool.py"}),
        ("See how other code in this repo uses the pool correctly.",
         "search", {"text": "report_pool.connection()"}),
        ("First, a regression test that reproduces the leak: after several requests nothing may stay checked out.",
         "write_file", {"path": REGRESSION_TEST_PATH, "content": REGRESSION_TEST}),
        ("Release the connection when the view is done.",
         "edit_file", {"path": VICTIM_FILE, "old_text": RETURN_LINE, "new_text": FLAWED_FIX}),
        ("Run the guardrails and the sandbox.",
         "run_tests", {}),
        ("The test still sees leaked connections: release() sits after `return`, so it never runs. "
         "Use the pool's context manager like top_pages does, so the connection is returned even on errors.",
         "edit_file", {"path": VICTIM_FILE, "old_text": LEAKY_BODY + FLAWED_FIX, "new_text": FIXED_BODY + RETURN_LINE}),
        ("Verify again.",
         "run_tests", {}),
        ("Tests pass and the regression test fails on the old code.",
         "finish", {
             "summary": "user_activity_report acquired a pooled database connection and never released it, so every "
                        "request left a session idle in transaction until PostgreSQL ran out of connections. The view "
                        "now uses `with report_pool.connection()`, which always returns the connection (even on errors), "
                        "and a regression test proves no connection stays checked out.",
             "risk": "Low",
             "risk_reason": "Three-line change that adopts the pool's existing context manager (already used by "
                            "top_pages); response format unchanged; full test suite passes.",
         }),
    ], name="victim-service-pool-leak")


def recording_for_fix(suspect: dict) -> ScriptedClient | None:
    loc = suspect.get("location", {})
    if loc.get("file") == VICTIM_FILE and loc.get("function") == "user_activity_report":
        return fix_recording()
    return None


# --- outer loop: merge conflict with the demo teammate change (demo/teammate.py) ---------
CONFLICT_BLOCK = '''<<<<<<< HEAD
    with report_pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
            "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
        )
        rows = cursor.fetchall()
=======
    conn = report_pool.acquire()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
        "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 100"
    )
    rows = cursor.fetchall()
>>>>>>> origin/main
'''

RESOLVED_BLOCK = '''    with report_pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
            "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 100"
        )
        rows = cursor.fetchall()
'''


def conflict_recording() -> ScriptedClient:
    return ScriptedClient([
        ("Look at the conflict markers.",
         "read_file", {"path": VICTIM_FILE}),
        ("Our side wraps the query in the pool's context manager; the teammate raised LIMIT 50 to 100 on the "
         "old leaky code. Keep both: context manager AND LIMIT 100.",
         "edit_file", {"path": VICTIM_FILE, "old_text": CONFLICT_BLOCK, "new_text": RESOLVED_BLOCK}),
        ("Re-verify the merged result.",
         "run_tests", {}),
        ("Merged cleanly; tests pass.",
         "finish", {
             "summary": "Merged the latest main into the fix branch. Kept the teammate's change (top 100 users) "
                        "and the leak fix (connection always returned via the context manager).",
             "risk": "Low",
             "risk_reason": "Conflict was limited to one query block; both intents preserved; suite passes.",
         }),
    ], name="victim-service-merge-conflict")


def recording_for_conflict(conflicts: dict[str, str]) -> ScriptedClient | None:
    """conflicts = {path: file text with markers}."""
    if set(conflicts) == {VICTIM_FILE} and CONFLICT_BLOCK in conflicts[VICTIM_FILE]:
        return conflict_recording()
    return None
