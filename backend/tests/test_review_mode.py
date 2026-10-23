"""Review vs Autonomous mode: human approval gates before mitigation and before code changes."""
import threading
import time

import pytest
from django.test import Client

from agent.approvals import ApprovalRequest, ScriptedApproval
from agent.pipeline import run_pipeline
from incidents.approvals import DjangoApprovalGate, record_decision
from incidents.models import AuditLog, Incident
from incidents.recorder import DjangoRecorder


def test_denied_mitigation_is_skipped_but_fix_continues(env):
    from .test_pipeline import make_deps

    deps, rec, _ = make_deps(env, scenario_kw={"conflict": False})
    deps.approvals = ScriptedApproval({"mitigation": False, "fix": True})
    state = run_pipeline("INC-E2E", {}, deps)
    assert state["outcome"] == "merged"
    assert rec.fields.get("mitigation") is None or rec.fields["mitigation"].get("terminated", 0) == 0
    assert deps.adapter.terminated == []  # no session was ended
    assert [r.gate for r in deps.approvals.asked] == ["mitigation", "fix"]
    gates = [(a["payload"]["gate"], a["payload"]["approved"]) for a in rec.audits if a["kind"] == "approval"]
    assert gates == [("mitigation", False), ("fix", True)]


def test_denied_fix_escalates_to_human(env):
    from .test_pipeline import make_deps

    deps, rec, _ = make_deps(env)
    deps.approvals = ScriptedApproval({"fix": False})
    state = run_pipeline("INC-E2E", {}, deps)
    assert state["outcome"] == "escalated"
    assert "handle the code fix manually" in rec.fields["escalation_reason"]
    assert rec.steps == []  # the coding agent never ran


def test_autonomous_mode_still_records_decisions(env):
    from .test_pipeline import make_deps

    deps, rec, _ = make_deps(env, scenario_kw={"conflict": False})
    run_pipeline("INC-E2E", {}, deps)
    modes = {a["payload"]["mode"] for a in rec.audits if a["kind"] == "approval"}
    assert modes == {"autonomous"}


@pytest.mark.django_db(transaction=True)
def test_django_gate_waits_for_dashboard_decision():
    inc = Incident.objects.create(dedupe_key="k", status="MITIGATING", approval_mode="review")
    rec = DjangoRecorder(inc.id)
    gate = DjangoApprovalGate(inc.id, rec, timeout_seconds=10, poll_seconds=0.05)
    result = {}

    worker = threading.Thread(target=lambda: result.setdefault("d", gate.request(
        ApprovalRequest("mitigation", "End 88 sessions?", {"sessions": 88}))))
    worker.start()
    for _ in range(100):
        inc.refresh_from_db()
        if inc.pending_approval.get("gate"):
            break
        time.sleep(0.05)
    assert inc.status == "AWAITING_APPROVAL" and inc.pending_approval["title"] == "End 88 sessions?"

    c = Client()
    wrong = c.post(f"/api/v1/incidents/{inc.id}/decision", {"gate": "fix", "decision": "approve"},
                   content_type="application/json")
    assert wrong.status_code == 409
    ok = c.post(f"/api/v1/incidents/{inc.id}/decision",
                {"gate": "mitigation", "decision": "approve", "by": "Priya", "note": "go"},
                content_type="application/json")
    assert ok.status_code == 200
    worker.join(5)

    d = result["d"]
    assert d.approved and d.by == "Priya" and d.note == "go"
    inc.refresh_from_db()
    assert inc.status == "MITIGATING" and inc.pending_approval == {}
    assert AuditLog.objects.filter(incident=inc, kind="approval_click").exists()


@pytest.mark.django_db(transaction=True)
def test_django_gate_times_out_safely():
    inc = Incident.objects.create(dedupe_key="k", status="PATCHING", approval_mode="review")
    gate = DjangoApprovalGate(inc.id, DjangoRecorder(inc.id), timeout_seconds=0.2, poll_seconds=0.05)
    d = gate.request(ApprovalRequest("fix", "Change code?"))
    assert not d.approved and d.timed_out
    with pytest.raises(ValueError):
        record_decision(Incident.objects.get(pk=inc.pk), "fix", "approve", "late")
