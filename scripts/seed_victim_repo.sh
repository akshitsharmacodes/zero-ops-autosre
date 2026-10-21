#!/bin/bash
set -e

REPO_DIR="${1:-$(cd "$(dirname "$0")/../victim_service" && pwd)}"

echo "==> Seeding git repository in: $REPO_DIR"

cd "$REPO_DIR"

# Clean any existing git tracking in victim_service
rm -rf .git
git init -b main

# Git author configuration for consistent demo history
export GIT_AUTHOR_NAME="Alice Architect"
export GIT_AUTHOR_EMAIL="alice@zero-ops.internal"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# Step 1: Base service commit
cat << 'EOF' > analytics/views.py
import logging
from django.http import JsonResponse
from .models import UserMetric

logger = logging.getLogger(__name__)

def health_check(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok", "service": "victim-service"})
EOF

git add manage.py requirements.txt pytest.ini victim_project/ analytics/__init__.py analytics/apps.py analytics/models.py analytics/views.py analytics/urls.py tests/test_health.py
GIT_COMMITTER_DATE="2026-10-18T10:00:00" GIT_AUTHOR_DATE="2026-10-18T10:00:00" git commit -m "feat: initial django setup and health endpoint"

# Step 2: Analytics summary commit
export GIT_AUTHOR_NAME="Bob Developer"
export GIT_AUTHOR_EMAIL="bob@zero-ops.internal"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

cat << 'EOF' > analytics/views.py
import logging
from django.http import JsonResponse
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
EOF

git add analytics/views.py
GIT_COMMITTER_DATE="2026-10-19T14:30:00" GIT_AUTHOR_DATE="2026-10-19T14:30:00" git commit -m "feat(analytics): add metrics summary endpoint"

# Step 3: Buggy commit introducing the unclosed cursor leak
export GIT_AUTHOR_NAME="Charlie Contributor"
export GIT_AUTHOR_EMAIL="charlie@zero-ops.internal"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

cat << 'EOF' > analytics/views.py
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
EOF

git add analytics/views.py tests/
GIT_COMMITTER_DATE="2026-10-20T09:15:00" GIT_AUTHOR_DATE="2026-10-20T09:15:00" git commit -m "perf(reports): add fast raw-sql user activity report"

echo "==> Victim git repo successfully seeded!"
git log --oneline --decorate -n 3
