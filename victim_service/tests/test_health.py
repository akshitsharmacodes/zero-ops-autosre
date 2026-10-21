import pytest
from django.test import Client

@pytest.mark.django_db
def test_health_check():
    client = Client()
    response = client.get('/health/')
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "victim-service"

@pytest.mark.django_db
def test_metrics_summary():
    client = Client()
    response = client.get('/api/metrics/summary/')
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "success"
    assert "total_metrics" in data
