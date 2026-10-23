from django.http import JsonResponse

from .models import UserActivity
from .pool import report_pool


def health(request):
    return JsonResponse({"status": "ok", "service": "victim-service"})


def top_pages(request):
    """Most viewed pages, computed with raw SQL through the reporting pool."""
    with report_pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT page, COUNT(*) AS views FROM analytics_useractivity "
            "GROUP BY page ORDER BY views DESC LIMIT 10"
        )
        rows = cursor.fetchall()
    return JsonResponse({"pages": [{"page": r[0], "views": r[1]} for r in rows]})


def metrics_summary(request):
    """Headline numbers computed with the ORM."""
    return JsonResponse({
        "status": "success",
        "total_events": UserActivity.objects.count(),
        "unique_users": UserActivity.objects.values("user_id").distinct().count(),
    })


def user_activity_report(request):
    """Per-user activity summary using fast raw SQL."""
    conn = report_pool.acquire()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, COUNT(*) AS events, MAX(created_at) AS last_seen "
        "FROM analytics_useractivity GROUP BY user_id ORDER BY events DESC LIMIT 50"
    )
    rows = cursor.fetchall()
    data = [{"user_id": r[0], "events": r[1], "last_seen": str(r[2])} for r in rows]
    return JsonResponse({"status": "success", "count": len(data), "data": data})
