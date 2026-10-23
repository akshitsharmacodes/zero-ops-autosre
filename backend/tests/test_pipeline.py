"""Phase 6: the full workflow incl. the outer loop (TC-8, TC-9, TC-13 offline)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.coding.llm import LLMUnavailable
from agent.pipeline import AgentDeps, PipelineConfig, run_pipeline
from agent.ports import MemoryRecorder
from correlation.correlator import GitCorrelator
from delivery.providers import DeliveryError, LocalProvider
from demo.teammate import push_teammate_change
from sandbox.runner import SubprocessSandbox
from workspace.gitcmd import git

from .fakes import FakeAdapter

LOG_LINES = [
    {"level": "INFO", "logger": "victim.request", "msg": "request", "path": "/api/reports/user-activity/",
     "status": 200, "view": "analytics.views.user_activity_report"},
    {"level": "WARNING", "logger": "analytics.pool", "msg": "report pool has 40 connections checked out"},
    {"level": "ERROR", "logger": "django.request", "msg": "Internal Server Error: /api/reports/user-activity/",
     "path": "/api/reports/user-activity/", "status": 500,
     "exc": 'File "/app/analytics/views.py", line 34, in user_activity_report\n'
            "psycopg2.OperationalError: FATAL: sorry, too many clients already"},
]


class Scenario:
    """Drives the outer loop: a teammate pushes a conflict, later a human merges."""

    def __init__(self, provider, recorder, conflict=True, merge=True):
        self.provider, self.rec = provider, recorder
        self.conflict, self.merge = conflict, merge
        self.sleeps = 0

    def sleep(self, _seconds):
        self.sleeps += 1
        ready_count = self.rec.statuses.count("READY_TO_MERGE")
        if self.conflict and ready_count == 1 and not getattr(self, "pushed", False):
            push_teammate_change(self.provider)
            self.pushed = True
        elif self.merge and ready_count >= (2 if self.conflict else 1):
            pr = sorted(Path(self.provider.store).glob("pr-*.json"))[-1]
            self.provider.human_merge(json.loads(pr.read_text())["number"])
        if self.sleeps > 50:
            raise RuntimeError("scenario did not converge")


@pytest.fixture
def env(seeded_repo, tmp_path):
    origin, clone = seeded_repo
    log = tmp_path / "victim.log"
    log.write_text("\n".join(json.dumps(line) for line in LOG_LINES) + "\n")
    provider = LocalProvider(origin, tmp_path / "prs")
    return origin, clone, provider, log, tmp_path


def make_deps(env, *, mode="cached", live_factory=None, provider=None, scenario_kw=None, adapter=None):
    origin, clone, local, log, tmp = env
    provider = provider or local
    rec = MemoryRecorder("INC-E2E")
    scenario = Scenario(local, rec, **(scenario_kw or {}))

    def no_live():
        raise LLMUnavailable("no API key configured for provider 'groq'")

    deps = AgentDeps(
        recorder=rec, adapter=adapter or FakeAdapter(leaked=88), log_path=str(log),
        correlator=GitCorrelator(clone), provider=provider, sandbox=SubprocessSandbox(timeout=120),
        mode=mode, live_client_factory=live_factory or no_live,
        config=PipelineConfig(pr_poll_seconds=0, pr_watch_timeout=600, deliveries_dir=tmp / "deliveries",
                              work_dir=tmp / "work", secret_values=["autosre_agent_pw"]),
        started_at=datetime.now(timezone.utc),
        baseline=lambda: {"total": 10, "active": 2, "idle": 8, "idle_in_transaction": 0},
        sleep=scenario.sleep,
    )
    return deps, rec, scenario


def test_full_loop_fix_pr_conflict_ready_merged_tc13(env):
    origin, clone, provider, log, tmp = env
    deps, rec, _ = make_deps(env)
    state = run_pipeline("INC-E2E", {"metric": "pg_connections", "value": 98, "source": "pg-monitor"}, deps)

    assert state.get("error") is None, state.get("error")
    assert state["outcome"] == "merged"
    assert rec.statuses == [
        "DIAGNOSING", "MITIGATING", "CORRELATING", "PATCHING",
        "TESTING_IN_SANDBOX", "PATCHING", "TESTING_IN_SANDBOX", "PATCHING",  # attempt 1 fails, attempt 2 passes
        "PR_CREATED", "READY_TO_MERGE",
        "UPDATING_PR", "TESTING_IN_SANDBOX", "PATCHING", "PR_CREATED",      # outer loop resolves the conflict
        "READY_TO_MERGE", "RESOLVED",
    ]
    # mitigation ended only the app's sessions
    assert rec.fields["mitigation"]["terminated"] == 88
    # correlation found Charlie
    assert rec.fields["suspect"]["commit"]["author"] == "Charlie Contributor"
    # fix verified with self-healing
    assert rec.fields["fix"]["attempts"] == 2 and rec.fields["fix"]["risk"] == "Low"
    # PR exists on the fix branch, never on main
    pr = rec.fields["pull_request"]
    assert pr["head_branch"] == "autosre/fix-inc-e2e" and pr["base_branch"] == "main"
    # the merged main contains BOTH the fix and the teammate's LIMIT 100
    views = git("show", "main:analytics/views.py", cwd=origin)
    assert "with report_pool.connection() as conn:" in views and "LIMIT 100" in views
    assert "report_pool.acquire()" not in views.split("def user_activity_report")[1]
    assert "<<<<<<<" not in views
    assert "tests/test_user_activity_releases_connection.py" in git("ls-tree", "-r", "--name-only", "main", cwd=origin)
    # post-mortem has all required sections (FR-7.4)
    body = rec.fields["postmortem"]
    for section in ("### Summary", "### Impact", "### Root cause", "### Fix", "### Verification", "### Timeline", "### Prevention"):
        assert section in body
    assert "NOT-isolated subprocess fallback" in body  # never claims isolation it did not have
    assert "autosre_agent_pw" not in json.dumps(rec.audits)  # secrets never reach prompts
    assert any(e["tag"] == "LOOP" and "repaired" in e["message"] for e in rec.events)


def test_llm_unreachable_falls_back_to_cached_tc8(env):
    deps, rec, _ = make_deps(env, mode="live", scenario_kw={"conflict": False})
    state = run_pipeline("INC-E2E", {}, deps)
    assert state["outcome"] == "merged"
    assert rec.fields["llm"]["fallback_used"] is True
    assert any("using CACHED" in e["message"] for e in rec.events)


def test_delivery_failure_saves_patch_locally_tc9(env):
    origin, clone, local, log, tmp = env

    class BrokenProvider(LocalProvider):
        def open_pr(self, *a, **kw):
            raise DeliveryError("GitHub API error: 502 Bad Gateway")

    deps, rec, _ = make_deps(env, provider=BrokenProvider(origin, tmp / "prs2"))
    state = run_pipeline("INC-E2E", {}, deps)
    assert state["outcome"] == "escalated"
    assert rec.statuses[-1] == "ESCALATED"
    bundle = tmp / "deliveries" / "INC-E2E"
    assert "with report_pool.connection()" in (bundle / "fix.patch").read_text()
    assert "human action required" in (bundle / "postmortem.md").read_text()


def test_unreachable_database_escalates(env):
    deps, rec, _ = make_deps(env, adapter=FakeAdapter(reachable=False))
    state = run_pipeline("INC-E2E", {}, deps)
    assert state["outcome"] == "escalated"
    assert "cannot read telemetry" in rec.fields["escalation_reason"]
