# AutoSRE API Contract (v1)

For the frontend. The backend is the source of truth. TypeScript types that mirror every shape below are in
[`frontend/src/types/api.ts`](../frontend/src/types/api.ts), and a ready-made fetch client is in [`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts).
You can reuse those or replace them.

- **Base URL:** `http://127.0.0.1:8000/api/v1` (set `VITE_API_BASE_URL=http://127.0.0.1:8000`)
- **CORS:** `http://localhost:5173` and `http://127.0.0.1:5173` are allowed (`CORS_ALLOWED_ORIGINS` in `.env`)
- **Auth:** none (local tool)
- **Times:** ISO-8601 UTC strings. **Durations:** seconds (number).

## 1. Envelope (every JSON response)

```json
{ "data": <payload or null>, "error": null | { "code": "STRING", "message": "human readable" }, "meta": { "timestamp": "2026-10-23T07:41:08Z" } }
```

Treat `error != null` or HTTP status ≥ 400 as a failure, and show `error.message` to the user.

| HTTP | `error.code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | unknown incident id |
| 400 | `INVALID_CONFIG` | bad PATCH /config values |
| 503 | `TELEMETRY_UNAVAILABLE` | the monitored PostgreSQL can't be reached |
| 503 | `VICTIM_UNREACHABLE` | demo trigger while the victim service is down |
| 409 | `NO_RECORDING`, `ALREADY_RUNNING`, `NOT_AVAILABLE`, `CANNOT_MERGE`, `BUSY` | demo actions not possible right now |

## 2. Enums

**IncidentStatus**, in normal order:
`ALERT_RECEIVED → DIAGNOSING → MITIGATING → CORRELATING → PATCHING ⇄ TESTING_IN_SANDBOX → PR_CREATED ⇄ UPDATING_PR → READY_TO_MERGE → RESOLVED`.
`ESCALATED` can happen from any state.

| Status | Meaning | Final? |
|---|---|---|
| `PATCHING` / `TESTING_IN_SANDBOX` | alternate during each fix attempt | no |
| `UPDATING_PR` | outer loop is repairing the PR (merge conflict or CI) | no |
| `READY_TO_MERGE` | agent finished; waiting for a human | no (watcher still running) |
| `RESOLVED` | a human merged the PR | **yes** |
| `ESCALATED` | handed to a human; see `escalation_reason` | **yes** |

**RunMode:** `cached` (recorded decisions, real tools) · `live` (real LLM) · `replay` (playback; nothing executes)

**Timeline tags:** `ALERT` `DIAG` `MITIGATE` `CORR` `PATCH` `AGENT` `GUARD` `TEST` `PR` `LOOP`

**Guardrail status:** `passed` · `failed` · `pending`

## 3. Endpoints

### System
| Method | Path | `data` |
|---|---|---|
| GET | `/health` | `{ status: "healthy", service, version }` |
| GET | `/system` | `SystemStatus` (below). Slow (~1–4 s) when the DB is down; poll every 10 s. |

```json
{ "mode": "cached",
  "llm": { "provider": "groq", "model": "llama-3.3-70b-versatile", "configured": false },
  "delivery": { "provider": "local", "target": "…/victim_origin.git", "configured": true },
  "sandbox": { "engine": "docker", "isolated": true, "setting": "auto" },
  "database": { "reachable": true, "error": null, "engine": "postgres", "host": "localhost" },
  "monitor": { "running": true, "last_error": null, "threshold": 0.9, "enabled": true },
  "victim": { "base_url": "http://localhost:8001" } }
```

### Alerts
`POST /alerts`. Body (all fields optional):
```json
{ "source": "pg-monitor", "severity": "critical", "metric": "pg_connections", "value": 98, "max": 100, "timestamp": "..." }
```
- `201` with `{ created: true, incident: IncidentSummary }`
- `200` with `{ created: false, incident }` when it's a duplicate for an open incident

### Incidents
| Method | Path | `data` |
|---|---|---|
| GET | `/incidents` | `IncidentSummary[]`, newest first, max 50 |
| GET | `/incidents/{id}` | `Incident` (summary + details + `timeline`) |
| GET | `/incidents/{id}/diff` | `{ incident_id, diff, suspect_commit_diff }` (unified diff strings, may be `""`) |
| GET | `/incidents/{id}/postmortem` | `{ incident_id, markdown }` (`""` until the PR opens or the incident escalates) |
| GET | `/incidents/{id}/steps` | `AgentStep[]`, the coding agent's tool calls |
| GET | `/incidents/{id}/sandbox-runs` | `SandboxRun[]` |
| GET | `/incidents/{id}/audit` | **file download** (`application/json`, no envelope) |
| POST | `/incidents/{id}/merge` | `{ merged: true, sha }`, the human-reviewer merge button (local provider only) |
| GET | `/incidents/{id}/stream` | **Server-Sent Events**, see §4 |

**IncidentSummary**
```json
{ "id": "INC-C966DE", "status": "READY_TO_MERGE", "mode": "cached", "source": "monitor",
  "alert": { "source": "autosre-monitor", "metric": "pg_connections", "value": 97, "max": 100, "severity": "critical" },
  "attempt": 2, "max_attempts": 3, "branch": "autosre/fix-inc-c966de",
  "pull_request": { "number": 1, "url": "local://victim_origin.git/pull/1", "state": "open", "draft": false,
                    "conflicts": false, "provider": "local", "head_branch": "autosre/fix-inc-c966de",
                    "base_branch": "main", "rounds": 0, "checks": "none", "title": "fix: … [INC-C966DE]" },
  "sandbox_isolated": true, "escalation_reason": "",
  "created_at": "…", "mitigated_at": "…", "pr_opened_at": "…", "ready_at": "…", "finished_at": null,
  "mttr_seconds": 38, "time_to_mitigate_seconds": 1 }
```
`pull_request` is `{}` until a PR exists. For GitHub, `url` is `https://github.com/...`. Nullable fields: every `*_at`, `mttr_seconds`, `time_to_mitigate_seconds`, `sandbox_isolated`.

**Incident** = IncidentSummary + these fields:
```json
{ "telemetry": { "total": 97, "max_connections": 100, "idle_in_transaction": 89, "utilization": 0.97, "by_application": {…} },
  "mitigation": { "terminated": 88, "app_prefix": "victim-service", "skipped_other_apps": 0, "after": { "total": 9, "max_connections": 100 }, "seconds_after_alert": 0.4 },
  "diagnosis": { "hypothesis": "…", "findings": ["…"], "leak_suspected": true,
                 "snapshot": {…}, "baseline": {…} | null, "delta": { "total": 87, … } | null,
                 "stuck_sessions": { "count": 89, "groups": [ { "application_name", "query", "example_query", "count", "max_idle_seconds", "pids" } ] },
                 "logs": { "errors": { "connection_exhaustion": 3 }, "readable": true, … } },
  "suspect": { "commit": { "sha", "short_sha", "author", "email", "date", "message" },
               "files": ["analytics/views.py", "analytics/urls.py"], "primary_file": "analytics/views.py",
               "location": { "file", "function", "start_line", "end_line", "snippet", "blame_ratio" },
               "confidence": 0.91, "score": 0.715, "evidence": ["…"], "candidates": [ { "sha", "author", "message", "score" } ] },
  "project_profile": { "language": "python", "source": "file", "test": "python -m pytest", "checks": ["…"] },
  "fix": { "summary", "risk": "Low|Medium|High", "risk_reason", "attempts": 2, "steps": 9,
           "tests": ["tests/test_…py"], "files": ["…"], "commit_sha": "…" },
  "llm": { "mode": "cached", "provider": "cached", "model": "scripted:…", "fallback_used": false, "fallback_reason": "" },
  "timeline": [ TimelineEntry ] }
```
Every object above is `{}` until its step has run, so render empty states.

**TimelineEntry:** `{ id: number, ts, tag, message, state: IncidentStatus }`. Ids increase; use them to dedupe.

**AgentStep:** `{ id, ts, task: "fix"|"resolve_conflict"|"fix_ci", attempt, step, thought, tool, args, ok, result }`.
`tool` is one of `list_files`, `read_file`, `search`, `edit_file`, `write_file`, `run_tests`, `finish`. `ok=false` means the tool or a guardrail refused.

**SandboxRun:** `{ id, ts, task, attempt, engine: "docker"|"subprocess", isolated, passed, reproduced: bool|null, exit_code, timed_out, duration_seconds, output, limits }`.
`reproduced=true` means the new regression test failed on the old code, which is what we want.

### Guardrails
`GET /guardrails?incident_id=INC-…` (omit the id to get the newest incident) returns `{ incident_id, checks: GuardrailCheck[] }`

```json
{ "id": "diff_size", "name": "Diff size (<= 50 changed lines)", "status": "passed", "passed": true, "details": "3 changed line(s) …", "attempt": 2 }
```
Ids, in order: `diff_size`, `file_allowlist`, `secret_scan`, `dangerous_patterns`, `syntax`, `sandbox_isolation`, `retry_cap`, `human_gate`.
Extra ids (for example `conflict_markers`) may be appended.

### Telemetry
| Method | Path | `data` |
|---|---|---|
| GET | `/telemetry/connections` | `{ active, idle, idle_in_transaction, other, total, max, utilization, by_application, live: true }`, or **503 `TELEMETRY_UNAVAILABLE`** |
| GET | `/telemetry/connections/history?minutes=10` | `[{ timestamp, active, idle, idle_in_transaction, total, max }]`, oldest first, one point per ~2 s (max 120 min) |

### Config
`GET /config` and `PATCH /config` both return `{ mode, max_attempts, llm_provider, alert_threshold, monitor_enabled }`.

PATCH accepts any subset:
- `mode`: `cached` | `live` | `replay`
- `max_attempts`: 1–5
- `llm_provider`: `groq` | `nvidia`
- `alert_threshold`: 0.5–1.0
- `monitor_enabled`: bool

Changes apply to **new** incidents.

### Demo controls
| Method | Path | Body | `data` |
|---|---|---|---|
| POST | `/demo/trigger` | `{ requests?: 400, concurrency?: 8 }` | `{ traffic: TrafficStatus, message }`. The monitor opens the incident by itself shortly after. |
| GET | `/demo/traffic` | | `{ sent, ok, errors, running, target, started_at }` |
| POST | `/demo/replay` | | `201 { incident }` (mode `replay`), or `409 NO_RECORDING` |
| POST | `/demo/teammate-push` | | `{ sha }`: pushes a conflicting change to main (local provider only) |
| POST | `/demo/reset` | `{ clear_incidents?: bool, reseed_repo?: bool }` | `{ traffic_stopped, sessions_ended, incidents_deleted?, repo_reseeded? }` |

## 4. Live stream (SSE)

`GET /incidents/{id}/stream`. Use the browser's `EventSource`, which reconnects automatically and resumes using `Last-Event-ID`.

| event | data | notes |
|---|---|---|
| `timeline` | `TimelineEntry` JSON | SSE `id:` = entry id; first sends the backlog, then new lines (< 1 s latency) |
| `status` | `{ "status": IncidentStatus }` | sent on connect and on every change |
| `end` | `{}` | incident is `RESOLVED` / `ESCALATED`; close the stream |

```js
const es = new EventSource(`${BASE}/api/v1/incidents/${id}/stream`)
es.addEventListener("timeline", (m) => addLine(JSON.parse(m.data)))
es.addEventListener("status",   (m) => setStatus(JSON.parse(m.data).status))
es.addEventListener("end",      () => es.close())
```

## 5. Suggested polling

| What | Interval |
|---|---|
| `/incidents` | 3 s |
| `/incidents/{id}` | 1.5 s while active, 10 s when final |
| `/telemetry/connections` + history | 2 s |
| `/guardrails`, `/steps`, `/sandbox-runs`, `/diff`, `/postmortem` | 2–3 s while active, once when final |
| `/system` | 10 s |

## 6. Must-show UI rules (from the SRS)

- **FR-9.3 transparency:** show a banner whenever `mode` is `cached` or `replay`, when `llm.fallback_used` is true, or when the sandbox is not isolated (`system.sandbox.isolated === false` or `incident.sandbox_isolated === false`).
- **FR-8.1:** status chips for at least Diagnosing, Patching, Testing and PR Created, colored green (done), yellow (active), grey (pending), red (failed).
- **FR-8.3:** dark mode. **FR-8.6:** live connection graph. **AO-1:** MTTR compared with ~45 min manual.
- Never show a "Merge" action for GitHub PRs; humans merge on GitHub. The merge button is local-provider only.
