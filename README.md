# AutoSRE (Team Zero-Ops)

**An autonomous on-call engineer.** AutoSRE detects a production database incident, stops the bleeding,
finds the commit that caused it, lets a coding agent write and **verify** a fix in a sealed sandbox,
opens a pull request with a post-mortem, and keeps that PR healthy (merge conflicts, failing CI) until it is
**ready to merge**. A human always presses Merge.

- **Tech-stack independent:** projects describe how to build and test themselves in `.autosre.yml`
  (or AutoSRE auto-detects Python / Node / Go / Java). Databases plug in through adapters (PostgreSQL first).
- **Our own coding agent:** a tool-using loop (read, search, edit, run tests, finish) on Groq or NVIDIA
  Nemotron. The guardrails live *inside the tools*, so the model can't bypass them.
- **Closed loop, twice:** an inner loop (fix, test, read the failure, fix again) and an outer loop
  (watch the PR, resolve conflicts, fix CI, stop at ready-to-merge).
- **Honest by design:** no fabricated telemetry or fake PRs. Cached, replay, LLM-fallback and non-isolated
  sandbox runs are always labeled on the dashboard and in the post-mortem.

New to these ideas? Read **[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)**, a plain-language guide to every step and decision.
The phase plan is in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## The workflow

```
alert ─▶ diagnose ─▶ stop the bleeding ─▶ find the commit ─▶ coding agent fixes ─▶ sandbox verifies ─▶ PR
                                                               ▲         │ fail: error fed back
                                                               └─────────┘ (max 3 attempts)
PR ─▶ watch: conflict? merge main + agent resolves │ CI red? agent fixes │ green ─▶ READY TO MERGE ─▶ human merges
any step out of budget / failing ─▶ ESCALATED to a human with the evidence bundle
```

## Quick start (Windows, macOS, Linux)

Prerequisites: Python 3.11+, Git 2.38+, Node.js 18+, Docker Desktop (running).

```bash
python scripts/setup.py
```

```bash
python scripts/dev.py
```

Open http://127.0.0.1:5173, then go to **Controls → Start incident**. Or run the whole story headless:

```bash
python scripts/demo.py --conflict --merge
```

`setup.py` creates `.venv`, installs dependencies, creates `.env`, migrates the database, seeds the
victim's git history, installs the dashboard, runs `docker compose up -d --build` (PostgreSQL 16 + the victim
service), and pre-builds the sandbox image. Without Docker it still works, but sandbox runs are **NOT isolated**
and are labeled that way.

### Live mode (real LLM) and real GitHub PRs

Edit `.env`:

```ini
AUTOSRE_MODE=live
LLM_PROVIDER=groq            # or nvidia
GROQ_API_KEY=...             # NVIDIA_API_KEY=... for Nemotron

DELIVERY_PROVIDER=github
GITHUB_REPO=your-user/victim-service
GITHUB_APP_ID=123456                         # AutoSRE's GitHub App (PRs by autosre[bot], 1-hour tokens)
GITHUB_APP_PRIVATE_KEY_PATH=secrets/github-app.pem
TARGET_REPO_PATH=var/victim_repo_github      # a local clone of that repo (AutoSRE reads history from it)
```

Then go to **Controls → Connect GitHub**. Full click-by-click guide: [docs/GITHUB_APP_SETUP.md](docs/GITHUB_APP_SETUP.md).
A fine-grained personal token (`GITHUB_TOKEN`) still works as a fallback.

If the LLM can't be reached during an incident, AutoSRE falls back to recorded decisions and says so.

## Repository layout

```
backend/                 Django 5 + DRF (ASGI/uvicorn)
  incidents/             models, REST API, SSE stream, monitor, runner, Django wiring, replay
  agent/pipeline.py      LangGraph workflow incl. the outer PR loop
  agent/coding/          coding agent: loop, tools (+guardrails), prompts, LLM clients, recordings
  telemetry/             database adapters (PostgreSQL)
  diagnostics/           log parser, diagnosis, stop-the-bleeding
  correlation/           commit scoring + git blame
  project/               .autosre.yml loader + stack auto-detection
  workspace/             temp clone / branch / merge helpers
  sandbox/               Docker sandbox (+ labeled subprocess fallback)
  guardrails/            rules shared by the agent tools and delivery
  delivery/              local + GitHub providers, post-mortem
  demo/                  traffic driver, teammate conflict simulation
victim_service/          demo patient: Django app with a real pool leak, .autosre.yml, tests
frontend/                Vite + React + TS dashboard
infra/postgres/          least-privilege roles (victim_app, autosre_agent)
scripts/                 setup.py, dev.py, demo.py, seed_victim_repo.py
```

## API (`/api/v1`, envelope `{data, error, meta}`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/system` | liveness; what is configured and reachable |
| POST | `/alerts` | alert webhook (SRS 6.3 payload); duplicates for an open incident are ignored |
| GET | `/incidents`, `/incidents/{id}` | list / full detail incl. timeline |
| GET | `/incidents/{id}/stream` | live timeline (Server-Sent Events, resumable) |
| GET | `/incidents/{id}/diff` · `/postmortem` · `/steps` · `/sandbox-runs` | fix diff, post-mortem, agent tool calls, sandbox runs |
| GET | `/incidents/{id}/audit` | full audit trail download (JSON) |
| POST | `/incidents/{id}/merge` | human reviewer's merge button (local provider only) |
| GET | `/guardrails?incident_id=` | guardrail checklist |
| GET | `/telemetry/connections`, `/telemetry/connections/history` | live and recent connection counts |
| GET/PATCH | `/config` | mode, LLM provider, max attempts, alert threshold |
| GET/POST | `/github/status` · `/github/connect` · `/github/callback` · `/github/disconnect` | GitHub App connection |
| POST | `/demo/trigger`, `/demo/replay`, `/demo/teammate-push`, `/demo/reset` | demo controls |

## Guardrails

| Rule | Enforcement |
|---|---|
| Only files from the suspect commit (+ new tests) | edit tools refuse, final gate re-checks |
| ≤ 50 changed source lines | final gate |
| No secrets (tokens, keys, passwords, configured values) | scrubbed before the LLM, blocked in patches |
| No `os.system`, `subprocess`, `eval`, `DROP`, `DELETE FROM`, … | edit tools + final gate (added lines) |
| Code parses, no leftover conflict markers | final gate |
| Regression test must fail on the old code, suite must pass on the new | sandbox, two phases |
| Sandbox: no network, no host mounts, non-root, caps dropped, 512 MB, 1 CPU, 120 s | Docker runner |
| Max 3 fix attempts, max 5 PR repair rounds, step and time budgets | agent loop + outer loop → escalate |
| Never push to `main`, never merge | provider guard + branch check; humans merge |
| Only the app's stuck DB sessions are ended | SQL re-checks app name, state, age; least-privilege role |

## Tests

```bash
.venv/Scripts/python -m pytest backend         # Windows (use .venv/bin/python elsewhere)
```

```bash
.venv/Scripts/python -m pytest victim_service
```

The backend suite covers SRS TC-1 to TC-14, including a full offline end-to-end run (fix, then PR, then a teammate
conflict, then the agent resolves it, then ready, then a human merges). Docker and PostgreSQL integration tests run automatically
when `docker compose up` is running, and skip otherwise.
