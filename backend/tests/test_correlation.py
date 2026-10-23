"""Phase 3 / TC-3: the correlator finds Charlie's commit and the exact leaking function."""
import pytest

from correlation.correlator import Clues, CorrelationFailed, GitCorrelator
from workspace.gitcmd import git

from .fakes import LEAK_QUERY

EVIDENCE = {
    "queries": [LEAK_QUERY],
    "application_names": ["victim-service:reports"],
    "endpoints": ["/api/reports/user-activity/"],
    "views": ["analytics.views.user_activity_report"],
    "loggers": ["analytics.pool"],
    "frames": [{"file": "/app/analytics/views.py", "line": 34, "function": "user_activity_report"}],
}


def test_clues_extract_distinctive_query_words():
    clues = Clues.from_evidence(EVIDENCE)
    assert {"analytics_useractivity", "user_id", "created_at", "last_seen", "events"} <= clues.query_tokens
    assert "select" not in clues.query_tokens
    assert "reports/user-activity" in clues.endpoint_fragments


def test_correlator_finds_leaking_commit_tc3(seeded_repo):
    _, clone = seeded_repo
    result = GitCorrelator(clone).correlate(EVIDENCE)

    assert result["commit"]["author"] == "Charlie Contributor"
    assert result["commit"]["message"].startswith("perf(reports)")
    assert result["primary_file"] == "analytics/views.py"
    assert set(result["files"]) == {"analytics/views.py", "analytics/urls.py"}
    loc = result["location"]
    assert loc["function"] == "user_activity_report"
    assert "report_pool.acquire()" in loc["snippet"]
    assert loc["blame_ratio"] == 1.0
    assert result["confidence"] >= 0.7
    assert result["candidates"][1]["author"] != "Charlie Contributor"
    assert "+    conn = report_pool.acquire()" in result["commit_diff"]


def test_correlation_with_query_only(seeded_repo):
    _, clone = seeded_repo
    result = GitCorrelator(clone).correlate({"queries": [LEAK_QUERY]})
    assert result["commit"]["author"] == "Charlie Contributor"


def test_correlation_fails_without_matching_evidence(seeded_repo):
    _, clone = seeded_repo
    with pytest.raises(CorrelationFailed):
        GitCorrelator(clone).correlate({"queries": ["SELECT * FROM billing_invoices WHERE overdue"]})


def test_correlation_uses_latest_origin(seeded_repo, tmp_path):
    origin, clone = seeded_repo
    # Someone pushes a newer commit to origin; the correlator must see it.
    other = tmp_path / "other"
    git("clone", "-q", str(origin), str(other), cwd=tmp_path)
    (other / "NOTES.md").write_text("notes\n")
    git("add", "-A", cwd=other)
    git("-c", "user.name=Eve", "-c", "user.email=eve@x", "commit", "-q", "-m", "docs: notes", cwd=other)
    git("push", "-q", "origin", "main", cwd=other)
    result = GitCorrelator(clone).correlate(EVIDENCE)
    assert result["base_sha"] == git("rev-parse", "HEAD", cwd=other).strip()
    assert result["commit"]["author"] == "Charlie Contributor"
