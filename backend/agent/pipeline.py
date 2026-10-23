"""
The AutoSRE workflow as a LangGraph state machine (SRS 3.2, extended with the outer loop).

    diagnose -> mitigate -> correlate -> fix -> deliver -> watch_pr -> END
        \\_________\\__________\\__________\\_______\\__________\\-> escalate -> END

Each node is a plain function (state, deps) -> partial state update, so every step can
be unit-tested on its own with fake dependencies (NFR-M3). Any failure routes to
`escalate`, which hands everything gathered so far to a human (FR-6.3, NFR-R2).
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.graph import END, StateGraph

from correlation.correlator import CorrelationFailed, GitCorrelator
from delivery.postmortem import render_postmortem
from delivery.providers import DeliveryError, DeliveryProvider, PRStatus
from diagnostics.diagnosis import build_diagnosis
from diagnostics.logs import summarize_log_file
from diagnostics.mitigation import stop_the_bleeding
from guardrails.rules import GuardrailPolicy, branch_check
from project.profile import ProfileError, load_profile
from telemetry import DatabaseAdapter, TelemetryUnavailable
from workspace.gitcmd import GitError, git
from workspace.workspace import Workspace

from .coding.briefing import CodeBriefing
from .coding.llm import ChatClient
from .coding.prompts import ci_task_prompt, conflict_task_prompt, fix_task_prompt, scrub, system_prompt
from .coding.recordings import recording_for_conflict, recording_for_fix
from .coding.session import run_coding_task
from .coding.tools import ToolBox
from .ports import Recorder

logger = logging.getLogger("autosre.pipeline")


class Escalate(Exception):
    """Raised by a node to hand the incident to a human with a clear reason."""


class PipelineState(TypedDict, total=False):
    incident_id: str
    alert: dict
    diagnosis: dict
    mitigation: dict
    suspect: dict
    fix: dict
    pr: dict
    error: str | None
    outcome: str


@dataclass
class PipelineConfig:
    app_prefix: str = "victim-service"
    idle_min_seconds: int = 5
    alert_threshold: float = 0.9
    base_branch: str = "main"
    max_attempts: int = 3
    max_steps: int = 30
    pr_max_rounds: int = 5
    pr_poll_seconds: float = 10
    pr_watch_timeout: float = 1800
    labels: list[str] = field(default_factory=lambda: ["autosre", "verified"])
    secret_values: list[str] = field(default_factory=list)
    deliveries_dir: Path = Path("var/deliveries")
    work_dir: Path | None = None
    keep_watching_when_ready: bool = True


@dataclass
class AgentDeps:
    recorder: Recorder
    adapter: DatabaseAdapter
    log_path: str
    correlator: GitCorrelator
    provider: DeliveryProvider
    sandbox: Any
    mode: str
    live_client_factory: Callable[[], ChatClient]
    config: PipelineConfig
    started_at: datetime
    baseline: Callable[[], dict | None] = lambda: None
    sleep: Callable[[float], None] = time.sleep
    ctx: dict = field(default_factory=dict)  # runtime objects (workspace, policy) shared between nodes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _secs_since(deps: AgentDeps) -> float:
    return (_now() - deps.started_at).total_seconds()


# --- nodes ---------------------------------------------------------------------------------
def node_diagnose(state: PipelineState, deps: AgentDeps) -> dict:
    rec, cfg = deps.recorder, deps.config
    rec.set_status("DIAGNOSING")
    rec.event("DIAG", "Reading live database activity (pg_stat_activity) and application logs...")
    try:
        snap = deps.adapter.snapshot()
        stuck = deps.adapter.stuck_sessions(cfg.idle_min_seconds)
    except TelemetryUnavailable as exc:
        raise Escalate(f"cannot read telemetry from the monitored database: {exc}") from exc
    logs = summarize_log_file(deps.log_path)
    diagnosis = build_diagnosis(snap, stuck, logs, deps.baseline(), cfg.alert_threshold)
    rec.update(telemetry=snap.as_dict(), diagnosis=diagnosis)
    for finding in diagnosis["findings"]:
        rec.event("DIAG", finding)
    if not logs.readable:
        rec.event("DIAG", f"Application log unavailable ({logs.note}); continuing with database evidence.")
    rec.event("DIAG", f"Hypothesis: {diagnosis['hypothesis']}")
    return {"diagnosis": diagnosis}


def node_mitigate(state: PipelineState, deps: AgentDeps) -> dict:
    rec, cfg = deps.recorder, deps.config
    rec.set_status("MITIGATING")
    try:
        stuck = deps.adapter.stuck_sessions(cfg.idle_min_seconds, cfg.app_prefix)
        if not stuck:
            rec.event("MITIGATE", f"No stuck '{cfg.app_prefix}' sessions to end; skipping stop-the-bleeding.")
            return {"mitigation": {"terminated": 0, "app_prefix": cfg.app_prefix}}
        result = stop_the_bleeding(deps.adapter, stuck, cfg.app_prefix, cfg.idle_min_seconds)
    except TelemetryUnavailable as exc:  # mitigation failing must not stop the real fix
        rec.event("MITIGATE", f"Stop-the-bleeding could not run ({exc}); continuing to the root-cause fix.")
        return {"mitigation": {"error": str(exc)}}
    after = result["after"]
    result["seconds_after_alert"] = round(_secs_since(deps), 1)
    rec.update(mitigation=result, mitigated_at=_now())
    rec.event("MITIGATE",
              f"Stop-the-bleeding: ended {result['terminated']} stuck '{cfg.app_prefix}*' sessions "
              f"(pg_terminate_backend). Connections now {after['total']}/{after['max_connections']}. "
              f"Other apps untouched ({result['skipped_other_apps']} skipped). The leak will return until the code is fixed.")
    return {"mitigation": result}


def node_correlate(state: PipelineState, deps: AgentDeps) -> dict:
    rec = deps.recorder
    rec.set_status("CORRELATING")
    rec.event("CORR", "Scoring recent commits against the evidence (query text, failing route, stack frames)...")
    try:
        _, git_env = deps.provider.clone_source()  # credentials for private repos
        suspect = deps.correlator.correlate(state["diagnosis"]["evidence"], git_env=git_env)
    except DeliveryError as exc:
        raise Escalate(f"cannot authenticate to the repository: {exc}") from exc
    except CorrelationFailed as exc:
        raise Escalate(f"could not identify the change that caused this: {exc}") from exc
    rec.update(suspect=suspect)
    c, loc = suspect["commit"], suspect["location"]
    rec.event("CORR", f"Suspect commit {c['short_sha']} by {c['author']}: \"{c['message']}\" "
                      f"(confidence {suspect['confidence']}).")
    if loc.get("start_line"):
        rec.event("CORR", f"Leaking code: {loc['file']} lines {loc['start_line']}-{loc['end_line']}"
                          + (f" in {loc['function']}()" if loc.get("function") else ""))
    for reason in suspect["evidence"][:3]:
        rec.event("CORR", f"Evidence: {reason}")
    return {"suspect": suspect}


def node_fix(state: PipelineState, deps: AgentDeps) -> dict:
    rec, cfg = deps.recorder, deps.config
    rec.set_status("PATCHING")
    suspect = state["suspect"]
    branch = f"autosre/fix-{state['incident_id'].lower()}"
    try:
        source, env = deps.provider.clone_source()
        ws = Workspace.create(source, cfg.base_branch, branch, parent_dir=cfg.work_dir, git_env=env,
                              author=deps.provider.commit_identity())
    except (GitError, DeliveryError) as exc:
        raise Escalate(f"could not create a workspace clone: {exc}") from exc
    deps.ctx["workspace"] = ws
    try:
        profile = load_profile(ws.root)
    except ProfileError as exc:
        raise Escalate(str(exc)) from exc
    policy = GuardrailPolicy(allowed_files=list(suspect["files"]), new_file_globs=[profile.test_file_glob],
                             secret_values=cfg.secret_values)
    deps.ctx.update(profile=profile, policy=policy)
    rec.update(project_profile=profile.as_dict(), branch=branch, sandbox_isolated=bool(deps.sandbox.isolated))
    rec.event("PATCH", f"Workspace ready: temporary clone on branch {branch} ({profile.language} project, "
                       f"build/test profile from {'.autosre.yml' if profile.source == 'file' else 'auto-detection'}).")
    if not deps.sandbox.isolated:
        rec.event("TEST", "WARNING: Docker is unavailable - sandbox runs are NOT ISOLATED (subprocess fallback).")

    briefing = CodeBriefing(ws).render(suspect.get("location", {}).get("file") or suspect["primary_file"])
    task, redacted = scrub(fix_task_prompt(state["incident_id"], state["diagnosis"], suspect, briefing),
                           cfg.secret_values)
    if redacted:
        rec.event("GUARD", f"Redacted {redacted} secret-like value(s) before sending context to the LLM.")
    rec.event("PATCH", f"Starting the coding agent ({deps.mode} mode, up to {cfg.max_attempts} test attempts).")

    def make_toolbox():
        return ToolBox(ws, profile, policy, deps.sandbox, rec, "fix", cfg.max_attempts, True,
                       on_attempt=lambda n: rec.update(attempt=n))

    result, brain = run_coding_task(
        mode=deps.mode, live_client_factory=deps.live_client_factory, recording=recording_for_fix(suspect),
        make_toolbox=make_toolbox, restart=ws.reset_hard, recorder=rec,
        system_prompt=system_prompt(profile, policy, cfg.max_attempts), task_prompt=task, max_steps=cfg.max_steps,
    )
    rec.update(llm=brain.as_dict())
    if not result.success:
        attempted = ws.diff() if ws.has_uncommitted_changes() else ""
        deps.ctx["attempted_diff"] = attempted
        raise Escalate(f"the coding agent could not produce a verified fix ({result.reason})")

    diff = ws.diff()
    title = result.summary.split(". ")[0][:72].rstrip(".")
    commit_sha = ws.commit_all(
        f"fix: {title}\n\n{result.summary}\n\nIncident: {state['incident_id']}\n"
        f"Suspect commit: {suspect['commit']['short_sha']}\nVerified by AutoSRE sandbox ({deps.sandbox.engine})."
    )
    sandbox = dict(result.last_sandbox or {})
    sandbox["output"] = (sandbox.get("output") or "")[-6000:]
    fix = {
        "summary": result.summary, "risk": result.risk, "risk_reason": result.risk_reason,
        "attempts": result.attempts, "steps": result.steps, "tests": result.created_tests,
        "files": sorted(ws.changed_files(ws.base_sha).keys()), "commit_sha": commit_sha,
        "sandbox": sandbox, "guardrails": result.last_guardrails, "brain": brain.as_dict(),
    }
    rec.update(fix=fix, unified_diff=diff)
    rec.event("PATCH", f"Verified fix committed after {result.attempts} attempt(s) [risk {result.risk}]: {result.summary[:220]}")
    return {"fix": fix}


def node_deliver(state: PipelineState, deps: AgentDeps) -> dict:
    rec, cfg = deps.recorder, deps.config
    ws: Workspace = deps.ctx["workspace"]
    gate = branch_check(deps.ctx["policy"], ws.branch)
    rec.guardrail(attempt=state["fix"]["attempts"], check_id=gate.id, name=gate.name, passed=gate.passed, details=gate.details)
    if not gate.passed:
        raise Escalate(gate.details)

    body = _postmortem(state, deps)
    title = f"fix: {state['fix']['summary'].split('. ')[0][:72].rstrip('.')} [{state['incident_id']}]"
    try:
        deps.provider.push(ws)
        pr = deps.provider.open_pr(head=ws.branch, base=cfg.base_branch, title=title, body=body, labels=cfg.labels)
    except (DeliveryError, GitError) as exc:
        saved = save_local_bundle(cfg.deliveries_dir, state["incident_id"], ws.diff(ws.base_sha), body)
        raise Escalate(f"delivery to {deps.provider.name} failed ({exc}); patch and post-mortem saved to {saved}") from exc

    pr_info = {**pr.__dict__, "provider": deps.provider.name, "rounds": 0, "title": title}
    rec.update(pull_request=pr_info, pr_opened_at=_now(), postmortem=body)
    rec.set_status("PR_CREATED")
    rec.event("PR", f"Draft pull request #{pr.number} opened: {pr.url} (branch {ws.branch}, labels "
                    f"{', '.join(cfg.labels)}). Human review required - AutoSRE never merges.")
    ws.cleanup()
    deps.ctx.pop("workspace", None)
    return {"pr": pr_info}


def node_watch_pr(state: PipelineState, deps: AgentDeps) -> dict:
    """Outer loop: keep the PR healthy until it is ready to merge (and then until a human merges it)."""
    rec, cfg, provider = deps.recorder, deps.config, deps.provider
    number = state["pr"]["number"]
    rounds, ready, errors = 0, False, 0
    deadline = time.monotonic() + cfg.pr_watch_timeout
    rec.event("LOOP", f"Watching PR #{number}: resolving conflicts and CI failures until it is ready to merge "
                      f"(max {cfg.pr_max_rounds} repair rounds).")

    while time.monotonic() < deadline:
        try:
            status = provider.get_pr(number)
            errors = 0
        except DeliveryError as exc:
            errors += 1
            if errors >= 5:
                raise Escalate(f"lost contact with {provider.name} while watching the PR: {exc}") from exc
            deps.sleep(cfg.pr_poll_seconds)
            continue

        if status.state == "merged":
            rec.update(pull_request={**state["pr"], **status.__dict__, "rounds": rounds})
            rec.set_status("RESOLVED")
            rec.event("PR", f"PR #{number} was merged by a human. Incident resolved.")
            return {"outcome": "merged"}
        if status.state == "closed":
            raise Escalate(f"PR #{number} was closed without merging")
        if status.mergeable is None:
            deps.sleep(min(cfg.pr_poll_seconds, 5))
            continue

        if status.conflicts:
            rounds += 1
            if rounds > cfg.pr_max_rounds:
                raise Escalate(f"PR still needs repairs after {cfg.pr_max_rounds} rounds")
            ready = False
            rec.set_status("UPDATING_PR")
            rec.event("LOOP", f"Round {rounds}: PR #{number} conflicts with the latest {cfg.base_branch}. Repairing...")
            _repair(state, deps, status, "resolve_conflict", rounds)
            rec.set_status("PR_CREATED")
            continue

        checks = provider.checks(status)
        if checks.state == "failure":
            rounds += 1
            if rounds > cfg.pr_max_rounds:
                raise Escalate(f"CI still failing after {cfg.pr_max_rounds} repair rounds")
            ready = False
            rec.set_status("UPDATING_PR")
            rec.event("LOOP", f"Round {rounds}: CI failed on PR #{number}:\n{checks.failure_text()[:600]}")
            _repair(state, deps, status, "fix_ci", rounds, ci_failures=checks.failure_text())
            rec.set_status("PR_CREATED")
            continue
        if checks.state == "pending":
            deps.sleep(cfg.pr_poll_seconds)
            continue

        if not ready:
            provider.mark_ready(number)
            ready = True
            rec.update(pull_request={**state["pr"], **status.__dict__, "draft": False, "rounds": rounds,
                                     "checks": checks.state})
            rec.set_status("READY_TO_MERGE")
            ci = "CI checks green" if checks.state == "success" else "no external CI configured; sandbox-verified"
            rec.event("PR", f"PR #{number} is READY TO MERGE ({ci}, no conflicts, {rounds} repair round(s)). "
                            f"Waiting for a human to merge.")
            if not cfg.keep_watching_when_ready:
                return {"outcome": "ready"}
        deps.sleep(cfg.pr_poll_seconds)

    if ready:
        rec.event("LOOP", f"Stopped watching PR #{number} after {cfg.pr_watch_timeout / 60:.0f} min; it remains ready to merge.")
        return {"outcome": "ready"}
    raise Escalate(f"PR #{number} did not become ready to merge within {cfg.pr_watch_timeout / 60:.0f} minutes")


def _repair(state: PipelineState, deps: AgentDeps, status: PRStatus, task: str, round_no: int,
            ci_failures: str = "") -> None:
    rec, cfg = deps.recorder, deps.config
    source, env = deps.provider.clone_source()
    ws = Workspace.create(source, cfg.base_branch, status.head_branch, parent_dir=cfg.work_dir, git_env=env,
                          author=deps.provider.commit_identity())
    try:
        old_base = git("merge-base", "HEAD", f"origin/{cfg.base_branch}", cwd=ws.root).strip()
        profile = load_profile(ws.root)
        fix = state["fix"]
        policy = GuardrailPolicy(allowed_files=sorted(set(state["suspect"]["files"]) | set(fix["tests"])),
                                 new_file_globs=[profile.test_file_glob], secret_values=cfg.secret_values)
        recording = None
        if task == "resolve_conflict":
            conflicted = ws.merge_base_branch()
            if not conflicted:
                deps.provider.push(ws)
                rec.event("LOOP", f"Latest {cfg.base_branch} merged cleanly into the fix branch; pushed.")
                return
            outside = [p for p in conflicted if p not in policy.allowed_files]
            if outside:
                raise Escalate(f"merge conflict in files AutoSRE may not edit: {', '.join(outside)}")
            rec.event("LOOP", f"Conflicted files: {', '.join(conflicted)}. Asking the coding agent to combine both sides.")
            recording = recording_for_conflict({p: ws.read_file(p) for p in conflicted})
            prompt = conflict_task_prompt(state["incident_id"], cfg.base_branch, conflicted, fix["summary"],
                                          ws.log_between(old_base, f"origin/{cfg.base_branch}"))

            def restart():
                ws.reset_hard()
                ws.merge_base_branch()
        else:
            prompt = ci_task_prompt(state["incident_id"], ci_failures)
            restart = ws.reset_hard
        prompt, _ = scrub(prompt, cfg.secret_values)

        def make_toolbox():
            tb = ToolBox(ws, profile, policy, deps.sandbox, rec, task, cfg.max_attempts, False,
                         diff_base=f"origin/{cfg.base_branch}", attempt_offset=fix["attempts"] + (round_no - 1) * cfg.max_attempts)
            tb.state.created_tests = list(fix["tests"])  # keep proving the bug against the new base
            return tb

        result, brain = run_coding_task(
            mode=deps.mode, live_client_factory=deps.live_client_factory, recording=recording,
            make_toolbox=make_toolbox, restart=restart, recorder=rec,
            system_prompt=system_prompt(profile, policy, cfg.max_attempts), task_prompt=prompt,
            max_steps=cfg.max_steps,
        )
        if not result.success:
            raise Escalate(f"could not {task.replace('_', ' ')} on PR #{status.number} ({result.reason})")
        if ws.merging():
            ws.complete_merge()
        else:
            ws.commit_all(f"fix: {task.replace('_', ' ')} for {state['incident_id']}\n\n{result.summary}")
        deps.provider.push(ws)
        diff = ws.diff(f"origin/{cfg.base_branch}")
        rec.update(unified_diff=diff, pull_request={**state["pr"], "rounds": round_no})
        what = "merge conflict" if task == "resolve_conflict" else "CI failure"
        deps.provider.comment(status.number, f"🤖 AutoSRE repaired a {what} (round {round_no}): {result.summary}\n\n"
                                             f"Re-verified in the sandbox ({deps.sandbox.engine}).")
        rec.event("LOOP", f"Round {round_no}: {what} repaired and pushed - {result.summary[:200]}")
    finally:
        ws.cleanup()


def node_escalate(state: PipelineState, deps: AgentDeps) -> dict:
    rec, cfg = deps.recorder, deps.config
    reason = state.get("error") or "unknown error"
    rec.set_status("ESCALATED")
    rec.update(escalation_reason=reason)
    report = _postmortem(state, deps, escalated=reason)
    diff = deps.ctx.get("attempted_diff", "")
    saved = save_local_bundle(cfg.deliveries_dir, state["incident_id"], diff, report)
    rec.update(postmortem=report)
    rec.event("ALERT", f"ESCALATED to the human on-call: {reason}. Evidence bundle: {saved}")
    ws = deps.ctx.pop("workspace", None)
    if ws:
        ws.cleanup()
    return {"outcome": "escalated"}


# --- helpers -----------------------------------------------------------------------------------
def _postmortem(state: PipelineState, deps: AgentDeps, escalated: str | None = None) -> str:
    fix = state.get("fix", {})
    mitigation = state.get("mitigation", {})
    ws = deps.ctx.get("workspace")
    diff = ""
    if ws and fix:
        diff = ws.diff(ws.base_sha)
    elif escalated:
        diff = deps.ctx.get("attempted_diff", "")
    return render_postmortem(
        incident_id=state["incident_id"], alert=state.get("alert", {}), diagnosis=state.get("diagnosis", {}),
        mitigation=mitigation, suspect=state.get("suspect", {}), fix=fix, diff=diff,
        sandbox=fix.get("sandbox"), guardrails=fix.get("guardrails", []), timeline=deps.recorder.timeline(),
        time_to_mitigate=mitigation.get("seconds_after_alert"), time_to_pr=None if escalated else _secs_since(deps),
        sandbox_isolated=getattr(deps.sandbox, "isolated", None), escalated_reason=escalated,
    )


def save_local_bundle(directory: Path, incident_id: str, diff: str, report: str) -> str:
    target = Path(directory) / incident_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "postmortem.md").write_text(report, encoding="utf-8")
    if diff:
        (target / "fix.patch").write_text(diff, encoding="utf-8")
    return str(target)


NODES = [
    ("diagnose", node_diagnose),
    ("mitigate", node_mitigate),
    ("correlate", node_correlate),
    ("fix", node_fix),
    ("deliver", node_deliver),
    ("watch_pr", node_watch_pr),
]


def build_graph(deps: AgentDeps):
    graph = StateGraph(PipelineState)

    def wrap(name, fn):
        def run(state: PipelineState) -> dict:
            try:
                return fn(state, deps) or {}
            except Escalate as exc:
                return {"error": str(exc)}
            except Exception as exc:  # NFR-R2: never crash silently
                logger.exception("node %s failed", name)
                deps.recorder.audit("error", {"node": name, "error": repr(exc), "traceback": traceback.format_exc()})
                return {"error": f"internal error during {name}: {exc}"}
        return run

    for name, fn in NODES:
        graph.add_node(name, wrap(name, fn))
    graph.add_node("escalate", wrap("escalate", node_escalate))
    graph.set_entry_point(NODES[0][0])

    for (name, _), (nxt, _) in zip(NODES, NODES[1:]):
        graph.add_conditional_edges(name, lambda s, nxt=nxt: "escalate" if s.get("error") else nxt,
                                    {"escalate": "escalate", nxt: nxt})
    last = NODES[-1][0]
    graph.add_conditional_edges(last, lambda s: "escalate" if s.get("error") else END, {"escalate": "escalate", END: END})
    graph.add_edge("escalate", END)
    return graph.compile()


def run_pipeline(incident_id: str, alert: dict, deps: AgentDeps) -> PipelineState:
    graph = build_graph(deps)
    try:
        return graph.invoke({"incident_id": incident_id, "alert": alert, "error": None},
                            {"recursion_limit": 50})
    finally:
        ws = deps.ctx.pop("workspace", None)
        if ws:
            ws.cleanup()
