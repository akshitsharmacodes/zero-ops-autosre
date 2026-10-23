from rest_framework.decorators import api_view

from ..services import ingest_alert
from .envelope import ok
from .serializers import IncidentSummarySerializer


@api_view(["GET"])
def health(request):
    return ok({"status": "healthy", "service": "autosre", "version": "2.0.0"})


@api_view(["POST"])
def receive_alert(request):
    """Alert webhook (FR-1.1). Duplicate alerts for an open incident return 200 with created=false."""
    incident, created = ingest_alert(request.data, source="webhook")
    return ok(
        {"created": created, "incident": IncidentSummarySerializer(incident).data},
        status=201 if created else 200,
    )
