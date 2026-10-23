"""
Background services started once per server process.

Started from asgi.py / wsgi.py (not AppConfig.ready) so that management commands,
migrations and tests never spawn background threads.
"""
import logging
import threading

logger = logging.getLogger("autosre.runtime")

_started = False
_lock = threading.Lock()


def start_background_services() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    _recover_interrupted_incidents()


def _recover_interrupted_incidents() -> None:
    """If the server stopped mid-incident, never leave it silently 'in progress' (NFR-R2)."""
    from django.db import OperationalError, ProgrammingError
    from django.utils import timezone

    from .models import ACTIVE_STATUSES, Incident, IncidentStatus, TimelineEvent

    try:
        stuck = list(Incident.objects.filter(status__in=ACTIVE_STATUSES))
    except (OperationalError, ProgrammingError):
        return  # database not migrated yet
    for inc in stuck:
        reason = "AutoSRE restarted while this incident was in progress."
        TimelineEvent.objects.create(incident=inc, tag="ALERT", message=f"ESCALATED: {reason}", state="ESCALATED")
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = reason
        inc.finished_at = timezone.now()
        inc.save(update_fields=["status", "escalation_reason", "finished_at", "updated_at"])
        logger.warning("Escalated interrupted incident %s", inc.id)
