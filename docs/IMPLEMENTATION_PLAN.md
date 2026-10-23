# AutoSRE — Implementation Plan (v2, agreed)

Source of truth: *AutoSRE Software Requirements Specification v1.0* (IDs like FR-x, NFR-x, TC-x, AO-x refer to it).
Plain-language walkthrough of the workflow: [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## Decisions

| Topic | Decision |
|---|---|
| Product scope | **Tech-stack independent.** The target project describes itself with `.autosre.yml`; when the file is missing, auto-detection takes over. Databases are reached through telemetry adapters (PostgreSQL first). |
| Demo patient | One Django + PostgreSQL victim app that **really** leaks connections. The traffic simulator only sends HTTP requests. |
| Fixing | **Our own coding agent**: a tool-using loop (list/read/search/edit files, run tests in the sandbox, finish). Guardrails are enforced inside the tools. |
| LLM | One OpenAI-compatible client. `LLM_PROVIDER=groq` (default) or `nvidia` (Nemotron). In **cached** mode a scripted "brain" plays back recorded decisions, and the tools still run for real. |
| Outer loop | After the PR is opened, keep watching it. Resolve merge conflicts with `main`, fix failing CI, and stop at **ready to merge**. A human merges. Every loop has a budget and escalates to a human when the budget runs out. |
| Delivery | `GitHubProvider` (PyGithub plus git push) for the real victim repo. `LocalProvider` (a bare git repo acting as "origin") lets the whole loop run offline without a token. |
| Backend | Django 5 + DRF, running under ASGI (uvicorn). AutoSRE keeps its own state in SQLite (WAL mode). Each incident runs in its own background thread. No Celery. |
| Sandbox | Docker by default: no host mounts, no network, non-root user, 512 MB memory, 1 CPU, 120 s limit. The subprocess fallback is clearly labeled **NOT ISOLATED**. |
| Frontend | Keep the Vite/React dashboard and wire it to the new API (mode banner, agent steps, outer-loop status). |
| Platform | Windows-first. All scripts are Python. |

## Architecture

```
backend/
  autosre_api/     settings, asgi, urls
  incidents/       Django app: models, REST API, SSE stream, services, monitor command
  agent/
    pipeline.py    LangGraph outer workflow (alert -> mitigate -> diagnose -> correlate -> fix -> deliver -> watch PR -> ready/escalate)
    coding/        our coding agent: loop, tools, prompts, LLM clients (openai-compatible + scripted)
  project/         .autosre.yml loader + stack auto-detection  (stack independence)
  telemetry/       database adapters (base + postgres)
  diagnostics/     log parsing + diagnosis summary
  correlation/     git history evidence scoring + blame
  guardrails/      rules shared by the agent tools and the delivery step
  workspace/       temp clone, branch, diff, commit, merge main, conflict detection
  sandbox/         docker runner + labeled fallback, driven by the project profile
  delivery/        LocalProvider, GitHubProvider, PR watcher helpers, post-mortem
  tests/
victim_service/    demo patient (with .autosre.yml)
scripts/           Python: seed repo, setup, demo runner
```

## Phases (one commit or more per phase on `feat/backend-rebuild`)

0. **Foundation:** Django project, models (Incident, TimelineEvent, AgentStep, SandboxRun, GuardrailResult, PullRequestState, AuditLog, TelemetrySample, RuntimeConfig), audit writer, env settings.
1. **Demo patient:** victim app with a real pool leak, `.autosre.yml`, JSON logs, migrations, tests, HTTP traffic simulator, a Python seed script that builds the history in a bare "origin" repo plus a working clone, and compose with Postgres 16 + least-privilege roles.
2. **Detect, mitigate, diagnose:** Postgres adapter, Alert Monitor (90% threshold), alert webhook + dedupe, stop-the-bleeding (victim sessions only), log parser, diagnosis summary with a baseline delta.
3. **Correlate:** commits from the last 20 / 7 days, scored by query-text, endpoint→file and stack-frame evidence; blame line range; confidence score.
4. **Project profile, workspace, sandbox:** `.autosre.yml` + detectors (python/node/go/java), temp clone + branch, Docker runner (two-phase run: the regression test must fail on the old code and the suite must pass on the new code).
5. **Coding agent:** tool loop, guardrail-checked tools, prompts with secret scrubbing, Groq/NVIDIA client, scripted cached brain, step budget, every step audited.
6. **Delivery + outer loop:** commit + push branch, open a draft PR with the post-mortem, then watch it. Conflicts → merge `main` → the agent resolves → sandbox → push. CI failure → the agent fixes. Green → mark ready. Budget exhausted → escalate. Includes a demo action that makes a teammate commit which conflicts.
7. **API + live stream + frontend:** keep the `/api/v1` contract and add the agent-steps / PR-loop / audit-export / replay endpoints. Update the dashboard.
8. **Tests + demo hardening:** TC-1..TC-14, unit tests per node/tool, replay fixture, setup/demo scripts, README.

## Waiting on you (not blocking early phases)
- Start Docker Desktop (needed from Phase 4).
- GitHub victim repo + fine-grained PAT (contents, pull requests, checks: read/write) — Phase 6 GitHub path.
- `GROQ_API_KEY` (and optionally `NVIDIA_API_KEY`) — live mode.
