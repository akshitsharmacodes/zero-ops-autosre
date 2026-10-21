from typing import TypedDict, List, Dict, Any, Optional

class TimelineEntry(TypedDict):
    ts: str
    tag: str   # ALERT | DIAG | CORR | PATCH | TEST | PR
    message: str
    state: str # ALERT_RECEIVED | DIAGNOSING | CORRELATING | PATCHING | TESTING_IN_SANDBOX | PR_CREATED | RESOLVED | ESCALATED

class AgentState(TypedDict):
    incident_id: str
    status: str
    attempt: int
    max_attempts: int
    alert_payload: Dict[str, Any]
    diagnostics_result: Dict[str, Any]
    suspect_commit: Dict[str, Any]
    leaking_code: str
    patch: str
    unified_diff: str
    risk: str
    confidence: float
    sandbox_result: Dict[str, Any]
    error_trace: Optional[str]
    guardrails_result: Dict[str, Any]
    pr_url: Optional[str]
    postmortem: Optional[str]
    timeline: List[TimelineEntry]
    mttr_seconds: int
    start_time: float
    mode: str
