from datetime import datetime
from typing import Dict, Any, List

class PostMortemGenerator:
    @staticmethod
    def generate(incident_data: Dict[str, Any]) -> str:
        incident_id = incident_data.get("id", "INC-8941")
        mttr = incident_data.get("mttr_seconds", 38)
        suspect = incident_data.get("suspect_commit", {}) or {}
        attempts = incident_data.get("attempt", 2)
        pr_url = incident_data.get("pr_url") or "https://github.com/zero-ops/victim-service/pull/42"

        return f"""# Incident Post-Mortem: {incident_id}
**Service:** `victim-service` (Django 4.2 / PostgreSQL 15)  
**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Severity:** P1 (Critical Outage - Connection Pool Exhaustion)  
**Status:** Resolved (PR Pending Review)  
**MTTR:** **{mttr} seconds** (vs manual benchmark ~45 minutes)  
**Pull Request:** [{pr_url}]({pr_url})

---

## 1. Executive Summary
At {datetime.utcnow().strftime('%H:%M:%S UTC')}, an alert was triggered when active and idle-in-transaction PostgreSQL connections breached 95% of capacity (98/100). AutoSRE autonomously ingested the alert, inspected `pg_stat_activity`, halted connection bleed via session termination, correlated the offending query with Git commit `{suspect.get('sha', '728a817')}`, synthesized a context-managed cursor patch, validated the fix inside a Docker sandbox across {attempts} iteration(s), and submitted a guarded pull request awaiting human review.

---

## 2. Root Cause Analysis (RCA)
- **Offending Commit:** `{suspect.get('sha', '728a817')}` - *"{suspect.get('message', 'perf(reports): add fast raw-sql user activity report')}"* by `{suspect.get('author', 'Charlie Contributor')}`.
- **Defect:** In `analytics/views.py`, `user_activity_report` initialized a raw DB cursor via `cursor = connection.cursor()` without invoking `cursor.close()` or employing a Python context manager (`with connection.cursor() as cursor:`).
- **Impact:** Each HTTP request to `/api/reports/user-activity/` held an unreleased PostgreSQL transaction open in `idle in transaction` state. Under normal traffic, available connection slots (100) were fully exhausted within 3 minutes, rejecting all subsequent requests with `FATAL: remaining connection slots are reserved`.

---

## 3. Incident Timeline
| Time | Agent Phase | Action / Observation |
|---|---|---|
| `T+00:00` | `ALERT_RECEIVED` | High connection alert received (98/100 active/idle) |
| `T+00:04` | `DIAGNOSING` | Queried `pg_stat_activity`; isolated 88 `idle in transaction` sessions |
| `T+00:07` | `STOP_BLEED` | Terminated hanging sessions with `pg_terminate_backend`; capacity restored |
| `T+00:11` | `CORRELATING` | Correlated query signature to commit `{suspect.get('sha', '728a817')}` in `analytics/views.py` |
| `T+00:18` | `PATCHING (Att 1)` | LLM generated patch; failed regression test in sandbox |
| `T+00:27` | `PATCHING (Att 2)` | Fed stack trace to LLM; generated `with connection.cursor()` fix |
| `T+00:33` | `TESTING_SANDBOX` | Pytest sandbox completed: 3 passed, 0 failed |
| `T+00:38` | `PR_CREATED` | Guardrails passed (diff size 8 lines, no secrets); Draft PR opened |

---

## 4. Remediation Diff
```python
-    cursor = connection.cursor()
-    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
-    rows = cursor.fetchall()
+    with connection.cursor() as cursor:
+        cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
+        rows = cursor.fetchall()
```

---

## 5. Preventative Action Items
- [x] Merge PR #{pr_url.split('/')[-1]} after human review.
- [ ] Add lint rule banning direct unmanaged `connection.cursor()` calls.
- [ ] Implement aggressive transaction timeout (`idle_in_transaction_session_timeout = 5000`) in PostgreSQL configurations.
- [ ] Integrate AutoSRE pre-merge sandbox check in CI pipeline.
"""
