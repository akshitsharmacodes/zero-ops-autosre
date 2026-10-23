"""Incident memory, personal-data redaction and the Responsible-AI card."""
import pytest

from agent.memory import InMemoryIncidentMemory, incident_signature, match_reason
from agent.pipeline import run_pipeline
from guardrails.rules import scrub_pii
from incidents.memory import DjangoIncidentMemory
from incidents.models import Incident

from .fakes import LEAK_QUERY

DIAG = {"stuck_sessions": {"groups": [{"query": LEAK_QUERY}]}}
SUSPECT = {"location": {"file": "analytics/views.py", "function": "user_activity_report"}}


def test_signature_matches_same_query_or_same_function():
    sig = incident_signature(DIAG, SUSPECT)
    assert sig["file"] == "analytics/views.py" and len(sig["query_hash"]) == 16
    assert match_reason(sig, dict(sig)) == "same stuck query"
    assert match_reason({**sig, "query_hash": "x"}, sig) == "same leaking function"
    assert match_reason({"query_hash": "x", "file": "a.py", "function": "f"}, sig) == ""


def test_pii_is_redacted_before_llm():
    text = "user alice@example.com from 203.0.113.7 paid with 4111 1111 1111 1111; local 127.0.0.1 ok"
    scrubbed, n = scrub_pii(text)
    assert n == 3
    assert "alice@" not in scrubbed and "203.0.113.7" not in scrubbed and "4111" not in scrubbed
    assert "127.0.0.1" in scrubbed  # loopback is not personal data


@pytest.mark.django_db
def test_django_memory_finds_past_incident():
    sig = incident_signature(DIAG, SUSPECT)
    Incident.objects.create(pk="INC-OLD", dedupe_key="k", status="RESOLVED", signature=sig,
                            pull_request={"url": "https://github.com/x/y/pull/7"}, fix={"summary": "used context manager"})
    Incident.objects.create(pk="INC-NEW", dedupe_key="k")
    found = DjangoIncidentMemory().similar("INC-NEW", sig)
    assert found[0]["id"] == "INC-OLD" and found[0]["pr_url"].endswith("/pull/7") and found[0]["match"] == "same stuck query"


def test_pipeline_records_memory_and_ai_card(env):
    from .test_pipeline import make_deps

    deps, rec, _ = make_deps(env, scenario_kw={"conflict": False})
    deps.memory = InMemoryIncidentMemory([{"id": "INC-OLD", "status": "RESOLVED", "match": "", "pr_url": "local://pull/1",
                                           "fix_summary": "context manager",
                                           "signature": {"query_hash": "", "file": "analytics/views.py",
                                                         "function": "user_activity_report"}}])
    run_pipeline("INC-E2E", {}, deps)

    assert rec.fields["related_incidents"][0]["id"] == "INC-OLD"
    assert any("Seen before" in e["message"] for e in rec.events)
    prompt = next(a["payload"]["user"] for a in rec.audits if a["kind"] == "prompt")
    assert '<untrusted_data source="past-incidents">' in prompt

    card = rec.fields["ai_card"]
    assert card["decision_maker"]["mode"] == "cached"
    assert card["data_shared"]["sent_to"].startswith("nobody (cached mode")
    assert "application-log-samples" in card["data_shared"]["evidence_sources"]
    assert card["human_oversight"]["decisions"][0]["gate"] == "mitigation"
    assert card["usage"]["agent_steps"] >= 5 and card["verification"]["regression_test_fails_on_old_code"] is True
    body = rec.fields["postmortem"]
    assert "### Responsible-AI card" in body and "### Seen before" in body and "Known limitations" in body
