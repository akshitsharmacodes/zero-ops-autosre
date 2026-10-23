# Competitive analysis: where AutoSRE stands (Oct 2026)

Based only on what each product's own pages say (read 23 Oct 2026). "Not stated" means the page doesn't say it, which isn't the same as "doesn't have it". Don't claim a competitor *lacks* something on stage; say "they don't publicly describe it".

## Products reviewed

| Product | What it is | Fix delivery | How it verifies fixes | Human control |
|---|---|---|---|---|
| **Azure SRE Agent** (Microsoft) | Incident investigation and mitigation across Azure, with memory | Infra actions (restart, scale); code PRs not described | Hypotheses checked against evidence; no sandbox/tests stated | Review vs Autonomous run modes, admin-only approval, RBAC, Tool Access Policies (allow/ask/deny), hooks |
| **Middleware OpsAI** | RCA across their observability stack | GitHub PR (apps); can apply fixes to K8s directly | Acts above 95% confidence; no tests stated | PR review for code; Auto-Fix mode for K8s |
| **OpenSRE** (open source) | CI/CD build-failure agent | PR plus fix report | "Confidence gate", mechanism not stated | "You review and merge"; asks when unsure |
| **GitHub Agentic Autofix** | Security (CodeQL) alert fixer | Draft PR | Re-runs CodeQL (not behavior tests) | Draft PR for review |
| **Aurora** (open source) | Investigation agent with 30+ tools, knowledge graph | One-click PR or run the fix | Not stated (sandboxed pods are for commands) | 4-layer command gate (injection rail, signatures, policy, LLM judge); fail-closed |
| **HealOps** (private beta) | "Incident in, diff out" | PR with regression test | Claims a reproducing test, CI, canary; sandbox not stated | Read-only, human merge, auditable trail |
| **SHIP** | Builder + Tester agents | PR | CI, code review, test on customer's preview | Optional checkpoint, auto-merge off by default |
| **Rootly** | Full incident-management platform with AI SRE | Drafts PRs after sign-off | Not stated | Explicit human sign-off, visible reasoning, PII redaction |

## What everyone does (table stakes)

- Start on an alert and correlate deploys, commits and telemetry into a root cause.
- Deliver fixes as PRs, with a **human merge gate**.
- Show evidence and confidence ("shows its work").
- Bring your own model / no training on customer data.
- Memory of past incidents and runbooks (Azure, Aurora, Rootly).
- Auto-generated post-mortems (Aurora, Rootly).

AutoSRE already covers all of these **except incident memory**.

## Where AutoSRE is genuinely different (safe to say on stage)

1. **Red-then-green proof in an isolated sandbox.** The regression test must *fail on the old code* and the full suite must *pass on the new code*, inside a container with no network, no host mounts and resource limits. HealOps claims a reproducing test, but none of the pages describe an isolated before/after run.
2. **It repairs its own PR until it's mergeable.** It resolves merge conflicts with `main` and fixes failing CI, then marks the PR ready. **No reviewed product describes this.**
3. **Stops the bleeding with least privilege.** It ends only the stuck sessions of the affected app, using a database role that can't read data. The SQL re-checks every condition at the moment of termination.
4. **Works with Wi-Fi down.** Cached mode replays recorded *decisions* while the tools still really run; replay mode plays back a recorded run. None describe a degraded/offline mode.
5. **Guardrails inside the tools, not after the fact.** A refused edit is returned to the agent with the reason, so the agent can't route around a rule.
6. **Radical honesty in the UI.** Banners whenever a run is cached, replayed, using an LLM fallback, or not isolated. The post-mortem never claims isolation it didn't have.
7. **Stack-independent by contract.** `.autosre.yml` (or auto-detection) tells it how to build and test any project.
8. **A robot identity, not your identity.** A GitHub App with per-repo install, minimal permissions, 1-hour tokens and PRs authored by `autosre[bot]`.

## Gaps to close (ranked by impact for judges ÷ effort)

| # | Feature | Who has it | Why it matters | Effort |
|---|---|---|---|---|
| 1 | **Prompt-injection defense**: logs, queries and code are attacker-controlled text; fence them as *data* and screen them (Groq offers `llama-prompt-guard-2` on our key) | Aurora (injection rail) | AI security; judges will ask "what if a log line says *ignore your rules*?" | S–M |
| 2 | **Review vs Autonomous mode**: optional human approval before stop-the-bleeding and before the agent starts coding | Azure, SHIP | Matches enterprise expectations; ethics (human agency) | S–M |
| 3 | **Incident memory**: "seen before: INC-x, same query signature, fixed by PR #n" | Azure, Aurora, Rootly | Table stakes; cheap with our DB | S |
| 4 | **Cost and token transparency**: tokens, model, $ estimate and time per incident | SHIP | Transparency + responsible AI | S |
| 5 | **Responsible-AI card** in every post-mortem: model, mode, what data left the machine (scrubbed), human checkpoints, limitations | nobody explicitly | AI ethics story in one artifact | S |
| 6 | **Post-merge verification**: watch telemetry after a merge; reopen if the leak returns | HealOps (canary) | Closes the loop on production, not just on tests | M–L (needs a redeploy step) |
| 7 | Policy-as-code allow/ask/deny in `.autosre.yml` | Azure, Aurora | Fine-grained control | M |
| 8 | Slack notification with PR link (SRS AO-8) | Aurora, HealOps, Rootly | Familiar workflow | S |

## One-line pitch

> "Others suggest a fix or open a PR. AutoSRE **proves** the fix with a red-then-green test in a sealed sandbox, **keeps its own PR mergeable** as `main` moves, and tells you honestly what it did, while a human still presses Merge."
