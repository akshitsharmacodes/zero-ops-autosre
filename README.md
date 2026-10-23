# AutoSRE — Team Zero-Ops

> **An autonomous on-call engineer** that detects a production database incident, stops the bleeding,
> finds the root-cause commit, lets a coding agent write and **verify** a fix inside a sealed sandbox,
> opens a pull request with a post-mortem, and keeps that PR healthy until it is **ready to merge**.
> A human always presses Merge.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Incident Pipeline](#incident-pipeline)
3. [Docker Composition](#docker-composition)
4. [How to Run](#how-to-run)
5. [Configuration](#configuration)
6. [Guardrails](#guardrails)
7. [API Reference](#api-reference)
8. [Tests](#tests)
9. [Repository Layout](#repository-layout)

---

## Architecture Overview

`mermaid
graph TB
    subgraph Infrastructure[Docker - docker-compose.yml]
        PG[PostgreSQL 16\nport 5432\nmax_connections=100]
        VS[Victim Service\nDjango app\nport 8001\npool leak bug]
        PG -- victim_app role --> VS
    end

    subgraph Host[Host Process - python scripts/dev.py]
        MON[Alert Monitor\npolls pg_stat_activity\nevery 2 s]
        BE[AutoSRE Backend\nDjango 5 + DRF + uvicorn\nport 8000]
        FE[Dashboard\nVite + React + TS\nport 5173]
        BE -- reads --> MON
    end

    subgraph Agent[Coding Agent - agent/coding/]
        LLM[LLM Client\nGroq / NVIDIA\ncached fallback]
        TOOLS[ToolBox\nread, search, edit\nwrite, run_tests, finish]
        GUARD[Guardrails\ninside tools\n+ injection screen]
        SBX[Sandbox\nDocker isolated\nsubprocess labeled]
        LLM --> TOOLS --> GUARD --> SBX
    end

    PG -- pg_stat_activity\nautosre_agent role --> MON
    VS -- logs to var/logs --> BE
    MON -- alert threshold >= 90% --> BE
    BE -- SSE stream --> FE
    BE -- spawns --> Agent
    Agent -- git push fix branch --> DEL[Delivery\nlocal bare repo\nor GitHub PR]
`

---

## Incident Pipeline

`mermaid
flowchart LR
    A([Alert\nWebhook or Monitor]) --> B[Diagnose\npg_stat_activity\nlog parsing]
    B --> C{Approval?\nreview mode}
    C -- autonomous --> D[Mitigate\nterminate stuck\nDB sessions]
    C -- review mode --> WAIT1([Human\nApproves])
    WAIT1 --> D
    D --> E[Correlate\ngit blame\ncommit scoring]
    E --> F{Approval?\nreview mode}
    F -- autonomous --> G[Coding Agent\nFix Loop]
    F -- review mode --> WAIT2([Human\nApproves])
    WAIT2 --> G

    subgraph G[Coding Agent - Inner Loop]
        direction TB
        G1[Read / Search / Edit] --> G2[Run Tests\nin Sandbox]
        G2 -- fail feeds back --> G1
        G2 -- pass --> G3[Finish]
    end

    G --> H[Deliver\nopen PR\npost-mortem]
    H --> I[Watch PR\nOuter Loop]

    subgraph I[Outer Loop]
        direction TB
        I1{PR healthy?} -- conflict --> I2[Agent resolves\nmerge conflict]
        I1 -- CI red --> I3[Agent fixes CI]
        I2 --> I1
        I3 --> I1
        I1 -- green --> I4([READY TO MERGE])
    end

    I4 --> MERGE([Human\nMerges PR])
    B -- any failure --> ESC([ESCALATED\nevidence bundle])
    G -- max 3 attempts --> ESC
    I -- max 5 rounds --> ESC
`

---

## Docker Composition

`mermaid
graph LR
    subgraph DC[docker-compose.yml]
        direction TB
        PG[postgres:16-alpine\nport 5432\nmax_connections=100\nsuperuser_reserved=1\nautosre_reserved=2\nVolume: postgres_data\nInit: infra/postgres/init.sql]
        VS[victim_service Dockerfile\nport 8001\nDjango + psycopg2 pool\nvar/logs mounted to /app/logs\ndepends_on postgres healthy]
        PG -- TCP 5432 --> VS
    end

    HOST[AutoSRE Backend\non host, port 8000]
    HOST -- autosre_agent read-only role --> PG
    HOST -- http://localhost:8001 --> VS
    HOST -- reads logs --> LOGS[var/logs/\nvictim.log]
    VS -- writes logs --> LOGS
`

### Roles provisioned by infra/postgres/init.sql

| Role | Permissions | Used by |
|---|---|---|
| ictim_app | INSERT/SELECT on nalytics_* | victim_service container |
| utosre_agent | SELECT on pg_stat_activity, pg_terminate_backend (guarded) | AutoSRE backend |
| pg_admin | Superuser | Docker init only |

---

## How to Run

### Option A — One-command demo (recommended, Docker required)

`ash
# 1. Clone
git clone https://github.com/akshitsharmacodes/Zero-Ops-AutoSRE.git
cd Zero-Ops-AutoSRE

# 2. Setup: creates .venv, .env, migrates DB, seeds victim history, builds containers
python scripts/setup.py

# 3. Start everything (backend + frontend together)
python scripts/dev.py
`

Open **http://127.0.0.1:5173** ? **Controls ? Start incident** and watch AutoSRE fix it.

---

### Option B — Headless end-to-end (CI / judges)

`ash
python scripts/demo.py --conflict --merge
`

Runs the full story without a browser:
1. Triggers the alert
2. AutoSRE diagnoses + mitigates + correlates + fixes
3. A simulated teammate pushes a conflicting commit
4. AutoSRE resolves the conflict and re-tests
5. Human merge is simulated (--merge)

---

### Option C — Docker only (manual host)

`ash
# Start just the database + victim service
docker compose up -d --build

# Start the backend
.venv/Scripts/python -m uvicorn autosre_api.asgi:application --app-dir backend --host 127.0.0.1 --port 8000

# Start the frontend
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
`

---

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | >= 3.11 | backend + scripts |
| Node.js | >= 18 | Vite dashboard |
| Git | >= 2.38 | victim repo seeding + agent workspace |
| Docker Desktop | latest | PostgreSQL + victim service + isolated sandbox |

> **Without Docker:** the system still works fully. Sandbox runs are labeled NOT ISOLATED on the dashboard and post-mortem. setup.py detects Docker's absence automatically.

---

### Victim Service (standalone)

The demo patient (ictim_service/) is a self-contained Django app with a **real connection-pool leak** in nalytics/views.py::user_activity_report. It can be run independently:

`ash
cd victim_service
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_activity
python manage.py runserver 8001
`

---

## Configuration

Copy .env.example to .env. Key settings:

`ini
# Mode
AUTOSRE_MODE=cached       # cached (no API key) | live (real LLM) | replay
SANDBOX_ENGINE=cached     # cached | auto | docker | subprocess

# LLM (live mode only)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_FALLBACK_MODELS=openai/gpt-oss-20b,qwen/qwen3.8-27b

# Delivery
DELIVERY_PROVIDER=local   # local (offline) | github (real PR)
GITHUB_REPO=your-user/victim-service
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=secrets/github-app.pem

# Monitored DB
TARGET_DB_HOST=localhost
TARGET_DB_PORT=5432
TARGET_DB_NAME=victim_db
TARGET_DB_USER=autosre_agent
TARGET_DB_PASSWORD=autosre_agent_pw
`

---

## Guardrails

`mermaid
flowchart TB
    INPUT[Untrusted input\nlogs, SQL text, commit msgs\nfile content, test output] --> FENCE[Step 1 - Fence as DATA\nwrapped in untrusted_data blocks\nsystem prompt: data is never instructions]
    FENCE --> SCREEN

    subgraph SCREEN[Step 2 - Injection Screen]
        H[HeuristicInjectionDetector - offline\n7 rule patterns:\n- override instructions\n- role hijack\n- fake chat markup\n- tool steering\n- secret exfiltration\n- hidden Unicode tricks]
        PG2[PromptGuardDetector\nMeta Llama Prompt Guard 2\nvia Groq API]
        H --> NEU[Neutralize\nreplace suspicious segment with notice\naudit logged]
        PG2 --> NEU
    end

    SCREEN --> TOOLS

    subgraph TOOLS[Step 3 - Tool Guardrails - enforced inside every tool call]
        R1[PathNotAllowed - no path traversal]
        R2[File allowlist - only suspect commit files + tests]
        R3[50 changed source lines maximum]
        R4[No dangerous patterns: os.system, subprocess, eval, DROP, DELETE FROM]
        R5[No secrets - scrubbed before LLM]
        R6[Code parses, no conflict markers]
        R7[Regression test must fail on old code, suite must pass on new code]
        R8[Never push to main, never merge]
    end

    TOOLS --> SAFE[Safe output to LLM / sandbox]
    TOOLS -- violation --> REFUSE[Refused + reason shown to model]
`

---

## API Reference

Base URL: http://127.0.0.1:8000/api/v1 · Envelope: { data, error, meta }

| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness check |
| GET | /system | Mode, LLM, delivery, sandbox, DB, monitor status |
| GET/PATCH | /config | Runtime config (mode, LLM provider, thresholds) |
| POST | /alerts | Ingest an alert (deduplicates open incidents) |
| GET | /incidents | List all incidents |
| GET | /incidents/{id} | Full incident detail + timeline |
| DELETE | /incidents/{id} | Remove incident + full audit trail |
| GET | /incidents/{id}/stream | Live SSE timeline (resumable) |
| GET | /incidents/{id}/diff | Agent unified diff |
| GET | /incidents/{id}/postmortem | Rendered post-mortem |
| GET | /incidents/{id}/steps | Agent tool calls |
| GET | /incidents/{id}/sandbox-runs | Sandbox execution records |
| GET | /incidents/{id}/audit | Full audit JSON export |
| POST | /incidents/{id}/stop | Force-stop running agent, status becomes ESCALATED |
| POST | /incidents/{id}/decision | Approve/Deny (review mode) |
| POST | /incidents/{id}/merge | Human merge (local provider) |
| GET | /guardrails?incident_id= | Guardrail checklist |
| GET | /telemetry/connections | Live DB connection counts |
| GET | /telemetry/connections/history | Historical connection samples |
| POST | /demo/trigger | Start background traffic to victim |
| POST | /demo/prototype | One-click: reset repo + trigger incident |
| POST | /demo/replay | Replay a recorded incident |
| POST | /demo/teammate-push | Simulate a conflicting commit |
| POST | /demo/reset | Wipe incidents + optionally reseed repo |
| GET/POST | /github/status, /github/connect, /github/callback, /github/disconnect | GitHub App OAuth flow |

---

## Tests

`ash
# Backend (SRS TC-1 through TC-14 + reliability + token budget)
.venv/Scripts/python -m pytest backend          # Windows
.venv/bin/python -m pytest backend              # macOS / Linux

# Victim service
.venv/Scripts/python -m pytest victim_service
`

> PostgreSQL and Docker integration tests auto-skip when the containers are not running.

---

## Repository Layout

`
Zero-Ops-AutoSRE/
+-- backend/
¦   +-- agent/
¦   ¦   +-- pipeline.py          LangGraph state machine (full incident workflow)
¦   ¦   +-- coding/              LLM client, tool loop, recordings, prompts
¦   +-- incidents/               Models, REST API, SSE, monitor, runner, wiring
¦   +-- telemetry/               PostgreSQL adapter (pg_stat_activity)
¦   +-- diagnostics/             Log parser, diagnosis, stop-the-bleeding
¦   +-- correlation/             Commit scoring + git blame
¦   +-- guardrails/              Injection screen + rule engine (inside tools)
¦   +-- sandbox/                 Docker sandbox + subprocess fallback
¦   +-- delivery/                Local bare repo + GitHub PR provider, post-mortem
¦   +-- workspace/               Temp clone, branch, diff helpers
¦   +-- project/                 .autosre.yml loader + stack auto-detection
¦   +-- demo/                    Traffic driver, teammate conflict simulation
+-- victim_service/              Demo target: Django app with real pool-leak bug
¦   +-- analytics/               Models, views (the leaky endpoint), pool
¦   +-- tests/                   Health, metrics, report tests
¦   +-- .autosre.yml             Tells AutoSRE how to build and test this project
+-- frontend/                    Vite + React + TypeScript live dashboard
+-- infra/postgres/              Least-privilege SQL roles init script
+-- scripts/
¦   +-- setup.py                 One-command environment bootstrap
¦   +-- dev.py                   Start backend + frontend together
¦   +-- demo.py                  Headless end-to-end demo runner
¦   +-- seed_victim_repo.py      Build the deterministic victim git history
+-- docs/
¦   +-- HOW_IT_WORKS.md          Plain-language guide (no code)
¦   +-- DEPLOY.md                Render + Vercel one-click deploy guide
¦   +-- GITHUB_APP_SETUP.md      Step-by-step GitHub App setup
+-- docker-compose.yml           PostgreSQL 16 + victim_service
+-- render.yaml                  Render Blueprint (hosted backend)
+-- .env.example                 All config knobs documented
`
