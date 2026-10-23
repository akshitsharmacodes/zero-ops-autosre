import pytest
from django.test import Client

from analytics.models import UserActivity


@pytest.mark.django_db
def test_metrics_summary_counts_events_and_users():
    UserActivity.objects.create(user_id=1, page="/home")
    UserActivity.objects.create(user_id=1, page="/pricing")
    UserActivity.objects.create(user_id=2, page="/home")

    body = Client().get("/api/metrics/summary/").json()
    assert body == {"status": "success", "total_events": 3, "unique_users": 2}
