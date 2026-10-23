"""
Human approval gates (Review vs Autonomous mode).

In Review mode the agent pauses before its two impactful steps and waits for a person:
  * "mitigation" - ending the application's stuck database sessions
  * "fix"        - letting the coding agent change code
The agent only depends on the ApprovalGate interface; the Django implementation stores
the request on the incident and waits for the dashboard's Approve / Deny.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Decision:
    approved: bool
    by: str = "autonomous mode"
    note: str = ""
    timed_out: bool = False


@dataclass
class ApprovalRequest:
    gate: str  # "mitigation" | "fix"
    title: str
    details: dict = field(default_factory=dict)


class ApprovalGate(Protocol):
    mode: str

    def request(self, req: ApprovalRequest) -> Decision: ...


class AutoApproval:
    """Autonomous mode: every gate is approved immediately (and still recorded)."""

    mode = "autonomous"

    def request(self, req: ApprovalRequest) -> Decision:
        return Decision(approved=True)


class ScriptedApproval:
    """For tests: answers gates from a dict {gate: approved?}."""

    mode = "review"

    def __init__(self, answers: dict[str, bool]):
        self.answers = answers
        self.asked: list[ApprovalRequest] = []

    def request(self, req: ApprovalRequest) -> Decision:
        self.asked.append(req)
        return Decision(approved=self.answers.get(req.gate, True), by="test reviewer")
