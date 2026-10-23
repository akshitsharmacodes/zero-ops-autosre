"""Runs each incident's agent workflow in its own background thread."""
from __future__ import annotations

import logging
import threading

from django.db import close_old_connections, connection

logger = logging.getLogger("autosre.runner")

_threads: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def launch(incident_id: str) -> threading.Thread:
    with _lock:
        existing = _threads.get(incident_id)
        if existing and existing.is_alive():
            return existing
        thread = threading.Thread(target=_run, args=(incident_id,), name=f"incident-{incident_id}", daemon=True)
        _threads[incident_id] = thread
    thread.start()
    return thread


def _run(incident_id: str) -> None:
    close_old_connections()
    try:
        from .wiring import run_incident

        run_incident(incident_id)
    except Exception:
        logger.exception("Incident %s crashed outside the pipeline", incident_id)
        _escalate_crash(incident_id)
    finally:
        connection.close()


def _escalate_crash(incident_id: str) -> None:
    from django.utils import timezone

    from .models import Incident, IncidentStatus, TimelineEvent

    reason = "AutoSRE hit an internal error; see audit log."
    Incident.objects.filter(pk=incident_id).update(
        status=IncidentStatus.ESCALATED, escalation_reason=reason, finished_at=timezone.now()
    )
    TimelineEvent.objects.create(incident_id=incident_id, tag="ALERT", state="ESCALATED", message=f"ESCALATED: {reason}")
