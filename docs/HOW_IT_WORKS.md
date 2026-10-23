# How AutoSRE Works — a plain-language guide

This guide grows as we build. Each section explains **what** a part does, **why** we need it, and **how** it fits the whole.

---

## 1. The story in one paragraph

A web app has a bug: every time someone opens a certain report, the app borrows a connection to the database and never gives it back. The database can only lend about 100 connections. After enough visits, the database says "too many clients", and the whole app goes down. Normally a tired engineer gets paged at 3 AM, digs through charts, logs and old code, writes a fix under pressure, and writes a report the next day. **AutoSRE does all of that by itself.** The one thing it leaves to people is pressing the final "Merge" button.

---

## 2. Words you'll see (kept simple)

| Word | Plain meaning |
|---|---|
| **Incident** | Something is broken right now and users are affected. |
| **Telemetry** | Live numbers about the system, such as "how many database connections are in use". |
| **Connection leak** | Code that borrows a database connection and forgets to return it. |
| **Commit** | One saved change in git, with an author, a time and a message. |
| **Branch** | A separate copy of the code where you can make changes without touching the main version. |
| **`main`** | The "official" branch that real users run. We never write to it directly. |
| **Pull request (PR)** | A formal request: "please review my branch and merge it into `main`". |
| **Merge conflict** | Two people changed the same lines differently, and git can't decide which one wins. |
| **CI** | Automatic tests that run on every PR (for example GitHub Actions). |
| **Sandbox** | A sealed, throwaway box (a Docker container) where untrusted code runs safely. |
| **Coding agent** | An AI that works like a developer: reads files, edits them, runs tests, and tries again. |
| **Guardrail** | A rule the AI is not allowed to break, checked by normal code rather than by the AI. |
| **Closed loop** | The system checks its own result and keeps correcting itself until the check passes. |
| **MTTR** | Mean Time To Recovery: how long it takes to get things healthy again. |

---

## 3. The workflow, step by step

```
 ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────────────────────┐
 │ 1 Alert │──▶│2 Mitigate│──▶│3 Diagnose│──▶│4 Correlate│──▶│ 5–8  Fix (inner loop)    │
 └─────────┘   └──────────┘   └──────────┘   └───────────┘   │ read → test → edit → run │
                                                              │ guardrails + sandbox     │
                                                              └────────────┬─────────────┘
                                                                           ▼
 ┌────────────────┐   ┌───────────────────────────────────────┐   ┌─────────────┐
 │ 11 Human merges│◀──│ 10 Watch PR (outer loop)               │◀──│ 9 Open PR   │
 └────────────────┘   │ conflict? → merge main → agent resolves│   └─────────────┘
                      │ CI red?   → agent fixes                 │
                      │ all green → "ready to merge"            │
                      └───────────────────────────────────────┘
          any loop out of budget ──▶ hand over to a human with all the notes
```

**1. Alert: notice the problem.**
A small watcher asks the database every couple of seconds how many connections are in use. Above 90%, it raises an alarm. Outside tools such as Prometheus or PagerDuty can also send an alarm to our web address. A second alarm about the same ongoing problem is ignored, so we never start two fixes at once.

**2. Mitigate: stop the bleeding.**
We end only the stuck connections that belong to the broken app, so users get service back within seconds. Think of first aid before surgery: it doesn't remove the cause, but it buys time.

**3. Diagnose: collect clues.**
- Which queries are stuck, and for how long?
- Which app opened them?
- What do the error logs say?
- How different is this from a normal, healthy moment?

**4. Correlate: find the change that caused it.**
We search recent commits for the clues, for example "which commit added this exact SQL query?". The result is a suspect commit, a file, line numbers, the author, and a confidence score. These files become the **only** files the agent may change.

**5. Workspace: make a safe copy.**
The code is copied into a temporary folder, and a new branch `autosre/fix-<incident>` is created there. The real code is never touched.

**6. Fix: the inner loop.**
The coding agent gets the clues and a small toolbox: *list files, read a file, search, edit a file, run tests, finish*. Like a careful developer, it:
1. reads the leaking code,
2. writes a test that proves the bug (this test must **fail** on the old code),
3. fixes the code,
4. runs all tests,
5. reads any failure and tries again, up to a step and attempt budget.

**7. Guardrails: rules it cannot break.**
Every edit goes through a checkpoint written in plain code, not AI. It can only touch the suspect files and new test files, change 50 lines at most, include no secrets, and use no dangerous commands such as `os.system` or `DROP TABLE`. A blocked edit comes back to the agent as "not allowed, because ...", so it has to find a better way.

**8. Sandbox: test in a sealed box.**
Tests run in a Docker container with no internet, no access to your computer's files, limited memory and CPU, and a 2-minute timer. The box is destroyed afterwards. Even a bad patch can't hurt anything.

**9. Deliver: open the pull request.**
The branch is pushed and a PR is opened. The PR description is the **post-mortem**: what broke, the impact, the timeline, the root cause, the fix, the proof, and how to prevent it next time.

**10. Watch the PR: the outer loop.**
While the PR waits for review, `main` keeps changing. Every ~30 seconds AutoSRE checks:
- **Merge conflict?** Pull the newest `main` into our branch, let the agent combine both versions sensibly, re-run the sandbox tests, and push.
- **CI failed?** Read the failure log, let the agent fix it, re-test, and push.
- **Everything green?** Mark the PR "ready to merge" and stop.

**11. A human merges.**
AutoSRE never merges by itself. People stay in charge of what reaches users.

**Why every loop has a budget.** An AI can go in circles. Each loop has a limit, for example 3 fix attempts, 5 conflict rounds, or a time limit. When the limit is reached, AutoSRE **escalates**: it hands everything it found and tried to a human.

---

## 4. How AutoSRE works with any tech stack

To work on a project, AutoSRE needs to know three things: how to install it, how to test it, and where the code lives. Each project can describe this in a small file called `.autosre.yml`:

```yaml
name: victim-service
language: python
image: python:3.11-slim          # which sealed box to use
install: pip install -r requirements.txt
test: python -m pytest -q
check: python manage.py check     # optional extra sanity check
source_dirs: [analytics, victim_project]
test_dir: tests
```

A Node.js project would say `npm ci` and `npm test`, and a Go project `go test ./...`. If the file is missing, AutoSRE **guesses** from the files it sees (`package.json` means Node, `requirements.txt` or `pyproject.toml` means Python, `go.mod` means Go, `pom.xml` means Java).

The same idea applies to databases. AutoSRE talks to them through **adapters**, small translators with the same questions ("how many connections?", "which are stuck?", "end these ones"). PostgreSQL is first. Adding MySQL later means writing one new adapter, without touching the rest.

---

## 5. Why these choices

| Choice | Why | What we gave up |
|---|---|---|
| Our own coding agent | We control every tool, so guardrails can't be skipped, and you learn how coding agents really work | Off-the-shelf agents (Aider, OpenHands) have more features |
| Groq by default (NVIDIA as backup) | Very fast responses keep the live demo snappy | Smaller models make more mistakes; the retry loop absorbs that |
| Cached "scripted brain" mode | The demo works without Wi-Fi or API keys, and the tools still really run | It's a recording of decisions, and the dashboard says so openly |
| Stop at "ready to merge" | Safety: a human approves what reaches users (SRS rule) | One manual click |
| Local "origin" repo as well as GitHub | The whole loop can be built and shown without a GitHub token | — |
| SQLite for AutoSRE's own data | The victim's database is the thing that is full, so we must not depend on it | Not meant for many servers at once (fine for this project) |

---

## 6. Build log: what we built and what to learn from it

### Phase 0: Foundation (memory and wiring)
- **What:** a Django project whose database stores *everything that happens*: incidents, every line on the live terminal, every agent step, every sandbox run, every guardrail verdict, and every prompt sent to the AI.
- **Why:** three features come almost for free once everything is written down. The dashboard reads it, the **audit trail** *is* it, and **replay mode** just plays it back.
- **Lesson:** AutoSRE keeps its own notes in SQLite, *not* in the app's PostgreSQL. During an incident, the app's database is exactly the thing that's full. A rescuer can't depend on the building that's on fire.
- **Lesson:** the agent code never talks to Django directly. It talks to a small **Recorder** interface ("write this event down"). In tests we swap in a recorder that keeps notes in a Python list. That's how every step stays testable on its own.

### Phase 1: The demo patient (a bug that is real)
- **What:** the victim app has a small **connection pool**, a shelf of reusable database connections. Correct code borrows one with `with report_pool.connection() as conn:`, and Python *always* puts it back when the block ends, even if there's an error. Charlie's new report calls `report_pool.acquire()` and never gives the connection back.
- **Why it's realistic:** this is exactly how real pool leaks happen. Every visit to that page keeps one more connection "idle in transaction" until PostgreSQL refuses new clients.
- **Lesson (permissions):** PostgreSQL has 100 seats. The app's account can't take the last 3. One is kept for the admin and two for AutoSRE's own account, so the rescuer can always get in. AutoSRE's account can *read statistics* and *end other sessions*, but it can't read or change the app's data. This is called **least privilege**.
- **Lesson (history):** the seed script builds a believable git history of 5 commits by 4 people. Charlie's leaky commit is *not* the newest one, so AutoSRE can't "cheat" by blaming the last commit.

### Phase 2: Detect, diagnose and stop the bleeding
- **Adapters:** the rest of AutoSRE asks the same three questions of any database ("how full?", "who is stuck?", "end these"). Only the PostgreSQL translator knows the PostgreSQL-specific SQL.
- **Safety detail:** before ending a session, the SQL **re-checks at that exact moment** that the session still belongs to the app, is still stuck, and has been stuck long enough. A DBA's own session is never touched. Our test proves it.
- **Duplicate alarms:** while an incident is open, new alarms about the same problem are written down and ignored, so we never run two fixes for one bug.
- **Logs:** the log reader picks out "too many clients" errors, the failing URLs, warning loggers, and, from error stack traces, the lines of *our* code involved (library code is ignored).

### Phase 3: Correlate (who changed what)
- **How:** for each recent commit, look only at the lines it **added**, and score them against the clues. The stuck query's distinctive words (table and column names) count most. Then come the function that served the failing URL, the URL itself, files in stack traces, and warning loggers.
- **Result on our demo:** Charlie's commit scores 0.715 against 0.216 for the next best, with **80% confidence**. `git blame` confirms that 100% of the leaking lines come from that commit.
- **Lesson:** confidence isn't just "how high is the score", it's also "how clearly did it win". A close race means lower confidence.
- **Lesson:** it's all text matching on diffs, so it works for any language. Python just gets a bonus step to find exact function boundaries.

*Next sections are added as each phase is built.*
