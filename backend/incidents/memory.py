"""Incident memory backed by the incidents table (signature stored on each incident)."""
from __future__ import annotations

from agent.memory import match_reason

from .models import Incident


class DjangoIncidentMemory:
    def remember(self, incident_id: str, signature: dict) -> None:
        Incident.objects.filter(pk=incident_id).update(signature=signature)

    def similar(self, incident_id: str, signature: dict, limit: int = 3) -> list[dict]:
        found = []
        candidates = Incident.objects.exclude(pk=incident_id).exclude(signature={}).order_by("-created_at")[:200]
        for inc in candidates:
            reason = match_reason(inc.signature, signature)
            if not reason:
                continue
            found.append({
                "id": inc.id, "status": inc.status, "created_at": inc.created_at.isoformat(), "match": reason,
                "pr_url": (inc.pull_request or {}).get("url"), "fix_summary": (inc.fix or {}).get("summary", ""),
            })
            if len(found) >= limit:
                break
        return found
