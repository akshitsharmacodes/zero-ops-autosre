"""
Incident memory: "have we seen this before?"

A *signature* identifies the kind of failure: the stuck query (normalized), the suspect
file and function. Past incidents with the same signature are surfaced on the timeline,
in the agent's context and in the post-mortem. A repeat after a merged fix is itself a
finding (the fix didn't hold, or the same mistake was made again).
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from diagnostics.diagnosis import normalize_query


def incident_signature(diagnosis: dict, suspect: dict) -> dict:
    groups = (diagnosis.get("stuck_sessions") or {}).get("groups") or []
    query = normalize_query(groups[0]["query"]) if groups else ""
    loc = suspect.get("location", {}) or {}
    return {
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16] if query else "",
        "file": loc.get("file") or suspect.get("primary_file", ""),
        "function": loc.get("function") or "",
    }


class IncidentMemory(Protocol):
    def remember(self, incident_id: str, signature: dict) -> None: ...

    def similar(self, incident_id: str, signature: dict, limit: int = 3) -> list[dict]:
        """Past incidents with the same signature: [{id, status, created_at, pr_url, fix_summary, match}]."""


class NoMemory:
    def remember(self, incident_id: str, signature: dict) -> None:
        pass

    def similar(self, incident_id: str, signature: dict, limit: int = 3) -> list[dict]:
        return []


class InMemoryIncidentMemory:
    """For tests and scripts."""

    def __init__(self, past: list[dict] | None = None):
        self.items: list[dict] = list(past or [])

    def remember(self, incident_id: str, signature: dict) -> None:
        self.items.append({"id": incident_id, "signature": signature})

    def similar(self, incident_id: str, signature: dict, limit: int = 3) -> list[dict]:
        return [i for i in self.items if i["id"] != incident_id and match_reason(i.get("signature", {}), signature)][:limit]


def match_reason(a: dict, b: dict) -> str:
    if a.get("query_hash") and a.get("query_hash") == b.get("query_hash"):
        return "same stuck query"
    if a.get("file") and a.get("file") == b.get("file") and a.get("function") and a.get("function") == b.get("function"):
        return "same leaking function"
    return ""
