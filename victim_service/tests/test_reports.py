from django.test import Client


def test_top_pages_returns_rows(fake_report_pool):
    response = Client().get("/api/reports/top-pages/")
    assert response.status_code == 200
    assert response.json()["pages"][0] == {"page": "/home", "views": 42}


def test_top_pages_returns_connection_to_pool(fake_report_pool):
    client = Client()
    for _ in range(3):
        client.get("/api/reports/top-pages/")
    stats = fake_report_pool.stats()
    assert stats["in_use"] == 0
    assert stats["opened"] == 1  # the same connection is reused
