"""
Replay mode (FR-9.2): play back a recorded real run, with its original timing.

Recording: `python manage.py export_replay <incident_id>` saves a finished run to
incidents/replay_data/recorded_run.json. Replay re-creates its timeline, agent steps,
sandbox runs and guardrail results on a new incident marked mode=replay, so the
dashboard shows a clear REPLAY banner (FR-9.3). Nothing is executed during replay.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import AgentStep, GuardrailResult, Incident, SandboxRun, TimelineEvent

RECORDING = Path(__file__).resolve().parent / "replay_data" / "recorded_run.json"

# Fields copied onto the incident once the replay reaches each state.
FIELDS_AT_STATE = {
    "MITIGATING": ["telemetry", "diagnosis"],
    "CORRELATING": ["mitigation"],
    "PATCHING": ["suspect", "project_profile", "branch", "sandbox_isolated", "llm"],
    "PR_CREATED": ["fix", "unified_diff", "attempt", "pull_request", "postmortem"],
    "READY_TO_MERGE": ["pull_request"],
    "RESOLVED": ["pull_request"],
}
INCIDENT_FIELDS = ["telemetry", "mitigation", "diagnosis", "suspect", "project_profile", "attempt", "fix",
                   "unified_diff", "branch", "pull_request", "postmortem", "llm", "sandbox_isolated", "escalation_reason"]


def recording_available() -> bool:
    return RECORDING.exists()


def export_incident(incident: Incident, path: Path = RECORDING) -> Path:
    start = incident.created_at

    def off(ts: datetime) -> float:
        return round((ts - start).total_seconds(), 2)

    items = []
    for e in incident.events.all():
        items.append({"t": off(e.ts), "kind": "event", "tag": e.tag, "message": e.message, "state": e.state})
    for s in incident.agent_steps.all():
        items.append({"t": off(s.ts), "kind": "step", "data": {k: getattr(s, k) for k in
                      ("task", "attempt", "step", "thought", "tool", "args", "ok", "result")}})
    for r in incident.sandbox_runs.all():
        items.append({"t": off(r.ts), "kind": "sandbox", "data": {k: getattr(r, k) for k in
                      ("task", "attempt", "engine", "isolated", "passed", "reproduced", "exit_code", "timed_out",
                       "duration_seconds", "output", "limits")}})
    for g in incident.guardrail_results.all():
        items.append({"t": off(g.ts), "kind": "guardrail", "data": {k: getattr(g, k) for k in
                      ("attempt", "check_id", "name", "passed", "details")}})
    items.sort(key=lambda i: i["t"])
    data = {
        "source_incident": incident.id,
        "recorded_at": timezone.now().isoformat(),
        "final_status": incident.status,
        "alert": incident.alert,
        "fields": {f: getattr(incident, f) for f in INCIDENT_FIELDS},
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    return path


def replay_into(incident: Incident, speed: float | None = None, sleep=time.sleep) -> None:
    data = json.loads(RECORDING.read_text(encoding="utf-8"))
    speed = speed or getattr(settings, "REPLAY_SPEED", 1.0)
    fields = data["fields"]
    Incident.objects.filter(pk=incident.pk).update(alert=data["alert"])
    TimelineEvent.objects.create(incident=incident, tag="ALERT", state="ALERT_RECEIVED",
                                 message=f"REPLAY of recorded run {data['source_incident']} - nothing is executed.")
    started, status = time.monotonic(), incident.status
    for item in data["items"]:
        wait = item["t"] / speed - (time.monotonic() - started)
        if wait > 0:
            sleep(min(wait, 10))
        if item["kind"] == "event":
            if item["state"] != status:
                status = item["state"]
                updates = {"status": status}
                for f in FIELDS_AT_STATE.get(status, []):
                    updates[f] = fields.get(f)
                if status == "MITIGATING":
                    updates["mitigated_at"] = timezone.now()
                if status == "PR_CREATED":
                    updates["pr_opened_at"] = timezone.now()
                if status == "READY_TO_MERGE":
                    updates["ready_at"] = timezone.now()
                if status in ("RESOLVED", "ESCALATED"):
                    updates["finished_at"] = timezone.now()
                Incident.objects.filter(pk=incident.pk).update(**updates)
            TimelineEvent.objects.create(incident=incident, tag=item["tag"], message=item["message"], state=item["state"])
        elif item["kind"] == "step":
            AgentStep.objects.create(incident=incident, **item["data"])
        elif item["kind"] == "sandbox":
            SandboxRun.objects.create(incident=incident, **item["data"])
        elif item["kind"] == "guardrail":
            GuardrailResult.objects.create(incident=incident, **item["data"])
    final = {f: fields.get(f) for f in INCIDENT_FIELDS if f != "escalation_reason" or fields.get(f)}
    final["status"] = data["final_status"]
    Incident.objects.filter(pk=incident.pk).update(**final)
