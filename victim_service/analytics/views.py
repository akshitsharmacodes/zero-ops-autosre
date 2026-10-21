import logging
from django.http import JsonResponse
from django.db import connection
from .models import UserMetric

logger = logging.getLogger(__name__)

def health_check(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok", "service": "victim-service"})

def metrics_summary(request):
    """Metrics summary endpoint using safe ORM queries."""
    count = UserMetric.objects.count()
    return JsonResponse({
        "status": "success",
        "total_metrics": count,
        "sample": "ok"
    })

def user_activity_report(request):
    """
    User activity report endpoint.
    BUG: Intentional connection/cursor leak!
    Opens raw connection cursor without context manager or cursor.close(),
    causing sessions to stay idle-in-transaction in PostgreSQL.
    """
    cursor = connection.cursor()
    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
    rows = cursor.fetchall()
    # Missing: cursor.close() or 'with connection.cursor() as cursor:'
    data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "success", "count": len(data), "data": data})
