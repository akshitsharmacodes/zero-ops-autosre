"""Phase 5: guardrails and the coding agent (TC-5, TC-6, TC-10, TC-11, TC-14)."""
import pytest

from agent.coding.llm import ScriptedClient
from agent.coding.loop import CodingAgent
from agent.coding.recordings import REGRESSION_TEST, REGRESSION_TEST_PATH, VICTIM_FILE, fix_recording
from agent.coding.tools import ToolBox
from agent.ports import MemoryRecorder
from guardrails.rules import GuardrailPolicy, branch_check, check_edit, evaluate_change, scrub_secrets
from project.profile import load_profile
from sandbox.runner import SubprocessSandbox
from workspace.gitcmd import parse_unified_diff
from workspace.workspace import Workspace

POLICY_KW = dict(allowed_files=["analytics/views.py", "analytics/urls.py"], new_file_globs=["tests/test_*.py"])


# --- guardrails ------------------------------------------------------------------------

def test_secret_scrubbing_tc14():
    text = ("token=ghp_" + "a" * 36 + " key gsk_" + "b" * 30 + "\n"
            'password = "hunter2hunter2"\npostgres://victim_app:s3cretpw@db:5432/x\nmy-env-secret-value')
    scrubbed, count = scrub_secrets(text, extra_values=["my-env-secret-value"])
    assert count == 5
    for leaked in ("ghp_", "gsk_", "hunter2", "s3cretpw", "my-env-secret-value"):
        assert leaked not in scrubbed
    assert 'password = "[REDACTED]"' in scrubbed


def _diff(path, added, removed=0, new=False):
    body = "".join(f"+line {i}\n" for i in range(added)) + "".join(f"-old {i}\n" for i in range(removed))
    head = "--- /dev/null\n" if new else f"--- a/{path}\n"
    return parse_unified_diff(f"diff --git a/{path} b/{path}\n{head}+++ b/{path}\n@@ -1,{removed} +1,{added} @@\n{body}")


def test_diff_size_limit_tc10():
    policy = GuardrailPolicy(**POLICY_KW)
    checks = {c.id: c for c in evaluate_change(policy, _diff("analytics/views.py", 40, 15), {})}
    assert not checks["diff_size"].passed and "55 changed line(s)" in checks["diff_size"].details
    ok = {c.id: c for c in evaluate_change(policy, _diff("analytics/views.py", 5, 4), {})}
    assert ok["diff_size"].passed


def test_new_test_files_have_their_own_budget():
    policy = GuardrailPolicy(**POLICY_KW)
    checks = {c.id: c for c in evaluate_change(policy, _diff("tests/test_new.py", 80, new=True), {})}
    assert checks["diff_size"].passed and checks["file_allowlist"].passed


def test_dangerous_patterns_tc11():
    policy = GuardrailPolicy(**POLICY_KW)
    for bad in ("    os.system('rm -rf /')", "    import subprocess", '    cur.execute("DROP TABLE users")',
                '    cur.execute("DELETE FROM analytics_useractivity")', "    eval(request.GET['x'])"):
        problems = check_edit(policy, "analytics/views.py", "x = 1\n", "x = 1\n" + bad + "\n")
        assert any("blocked patterns" in p for p in problems), bad
    assert check_edit(policy, "analytics/views.py", "x = 1\n", "x = 2\n") == []


def test_allowlist_blocks_other_files_and_new_files_outside_tests():
    policy = GuardrailPolicy(**POLICY_KW)
    assert check_edit(policy, "victim_project/settings.py", "a\n", "b\n")
    assert check_edit(policy, "analytics/new_module.py", None, "x = 1\n")
    assert check_edit(policy, "tests/test_regression.py", None, "def test_x(): pass\n") == []


def test_syntax_and_branch_checks():
    policy = GuardrailPolicy(**POLICY_KW)
    checks = {c.id: c for c in evaluate_change(policy, _diff("analytics/views.py", 1),
                                               {"analytics/views.py": "def broken(:\n"})}
    assert not checks["syntax"].passed
    assert not branch_check(policy, "main").passed and branch_check(policy, "autosre/fix-1").passed


# --- agent -------------------------------------------------------------------------------

@pytest.fixture
def toolbox_factory(seeded_repo, tmp_path):
    origin, _ = seeded_repo
    made = []

    def make(max_attempts=3, require_regression_test=True):
        ws = Workspace.create(str(origin), "main", "autosre/fix-test", parent_dir=tmp_path / "ws")
        rec = MemoryRecorder()
        tb = ToolBox(ws, load_profile(ws.root), GuardrailPolicy(**POLICY_KW), SubprocessSandbox(timeout=120),
                     rec, task="fix", max_attempts=max_attempts, require_regression_test=require_regression_test)
        made.append(tb)
        return tb, rec

    yield make
    for tb in made:
        tb.cleanup()
        tb.ws.cleanup()


def test_tools_refuse_unsafe_actions(toolbox_factory):
    tb, rec = toolbox_factory()
    ok, out = tb.execute("edit_file", {"path": "victim_project/settings.py", "old_text": "ROOT_URLCONF", "new_text": "X"})
    assert not ok and "Guardrail refused" in out
    ok, out = tb.execute("write_file", {"path": "analytics/helper.py", "content": "x = 1"})
    assert not ok and "new files may only be created" in out
    ok, out = tb.execute("read_file", {"path": "../../etc/passwd"})
    assert not ok and "PathNotAllowed" in out
    ok, out = tb.execute("edit_file", {"path": VICTIM_FILE, "old_text": "not in file", "new_text": "y"})
    assert not ok and "not found" in out
    ok, out = tb.execute("run_tests", {})
    assert not ok and "regression test" in out
    ok, out = tb.execute("finish", {"summary": "done", "risk": "Low", "risk_reason": "-"})
    assert not ok and "run_tests must pass" in out
    assert any(e["tag"] == "GUARD" for e in rec.events)


def test_agent_self_heals_on_second_attempt_tc5(toolbox_factory):
    tb, rec = toolbox_factory()
    result = CodingAgent(fix_recording(), tb, rec).run("system", "task")

    assert result.success, result.reason
    assert result.attempts == 2
    assert result.risk == "Low" and "context manager" not in result.reason
    assert result.created_tests == [REGRESSION_TEST_PATH]
    first, second = rec.sandbox_runs
    assert first["result"]["passed"] is False and first["result"]["reproduced"] is True
    assert "never returned to the pool" in first["result"]["output"]
    assert second["result"]["passed"] is True and second["result"]["reproduced"] is True

    diff = tb.ws.diff()
    assert "+    with report_pool.connection() as conn:" in diff
    assert "release(conn)" not in diff
    assert tb.ws.read_file(REGRESSION_TEST_PATH) == REGRESSION_TEST
    assert {g["check_id"] for g in rec.guardrails} >= {"diff_size", "file_allowlist", "dangerous_patterns", "secret_scan"}
    assert [s["tool"] for s in rec.steps][:4] == ["read_file", "read_file", "search", "write_file"]


def test_agent_escalates_after_max_attempts_tc6(toolbox_factory):
    tb, rec = toolbox_factory(max_attempts=3)
    write = ("write a test", "write_file", {"path": REGRESSION_TEST_PATH, "content": REGRESSION_TEST})
    run = ("try", "run_tests", {})
    result = CodingAgent(ScriptedClient([write, run, run, run, run]), tb, rec).run("s", "t")
    assert not result.success
    assert result.attempts == 3 and "all 3 test attempts failed" in result.reason
    assert len(rec.sandbox_runs) == 3


def test_agent_rejects_test_that_does_not_reproduce(toolbox_factory):
    tb, rec = toolbox_factory(max_attempts=1)
    useless = "def test_nothing():\n    assert True\n"
    script = ScriptedClient([("w", "write_file", {"path": "tests/test_useless.py", "content": useless}),
                             ("r", "run_tests", {}), ("f", "finish", {"summary": "s", "risk": "Low", "risk_reason": "r"})])
    result = CodingAgent(script, tb, rec).run("s", "t")
    assert not result.success
    assert rec.sandbox_runs[0]["result"]["reproduced"] is False
