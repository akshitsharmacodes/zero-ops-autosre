"""
"Ports" = the small interfaces the agent talks through.

The agent never imports Django models directly. It talks to a Recorder (where to write
what happened). That keeps every agent step a plain function we can unit-test with an
in-memory recorder (NFR-M3), and keeps the agent independent of the web framework.
"""
from __future__ import annotations

from typing import Any, Protocol


class Recorder(Protocol):
    incident_id: str

    def event(self, tag: str, message: str, **data: Any) -> None:
        """A human-readable line for the live terminal."""

    def set_status(self, status: str) -> None:
        """Move the incident to a new state (also writes an audit 'transition')."""

    def update(self, **fields: Any) -> None:
        """Store results on the incident (diagnosis, suspect, fix, pull_request, ...)."""

    def agent_step(self, *, task: str, attempt: int, step: int, tool: str, args: dict,
                   ok: bool, result: str, thought: str = "") -> None:
        """One tool call made by the coding agent."""

    def sandbox_run(self, *, task: str, attempt: int, result: dict) -> None:
        """One sandbox execution (engine, isolation, exit code, output...)."""

    def guardrail(self, *, attempt: int, check_id: str, name: str, passed: bool, details: str) -> None:
        """One guardrail verdict."""

    def audit(self, kind: str, payload: dict) -> None:
        """Append-only audit record (prompts, responses, patches, decisions)."""

    def timeline(self) -> list[dict]:
        """All timeline events so far (for the post-mortem)."""


class MemoryRecorder:
    """Recorder that keeps everything in lists. Used by unit tests and scripts."""

    def __init__(self, incident_id: str = "INC-TEST"):
        self.incident_id = incident_id
        self.status = "ALERT_RECEIVED"
        self.fields: dict[str, Any] = {}
        self.events: list[dict] = []
        self.steps: list[dict] = []
        self.sandbox_runs: list[dict] = []
        self.guardrails: list[dict] = []
        self.audits: list[dict] = []
        self.statuses: list[str] = []

    def event(self, tag, message, **data):
        from datetime import datetime, timezone

        self.events.append({"ts": datetime.now(timezone.utc).isoformat(), "tag": tag, "message": message,
                            "state": self.status, **data})

    def set_status(self, status):
        self.status = status
        self.statuses.append(status)

    def update(self, **fields):
        self.fields.update(fields)

    def agent_step(self, **kw):
        self.steps.append(kw)

    def sandbox_run(self, **kw):
        self.sandbox_runs.append(kw)

    def guardrail(self, **kw):
        self.guardrails.append(kw)

    def audit(self, kind, payload):
        self.audits.append({"kind": kind, "payload": payload})

    def timeline(self):
        return list(self.events)
