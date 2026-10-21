from unittest.mock import patch
import pytest
from django.test import Client
from django.db import connection

@pytest.mark.django_db
def test_user_activity_report_closes_cursor():
    """
    Regression test for CVE/incident AUTOSRE-101:
    Verifies that the user-activity report endpoint closes its database cursor.
    Fails if a cursor is opened and never closed or context-managed.
    """
    client = Client()
    real_cursor = connection.cursor
    tracked_cursors = []

    def tracking_cursor(*args, **kwargs):
        c = real_cursor(*args, **kwargs)
        c._was_closed = False
        original_close = c.close

        def close_wrapper(*a, **kw):
            c._was_closed = True
            return original_close(*a, **kw)

        c.close = close_wrapper
        tracked_cursors.append(c)
        return c

    with patch.object(connection, 'cursor', side_effect=tracking_cursor):
        response = client.get('/api/reports/user-activity/')
        assert response.status_code == 200

    assert len(tracked_cursors) > 0, "Expected at least one cursor to be opened in user_activity_report"

    # Verify that every opened cursor was properly closed
    for idx, c in enumerate(tracked_cursors):
        is_closed = getattr(c, '_was_closed', False)
        assert is_closed, (
            f"Cursor #{idx+1} opened in user_activity_report was NOT closed! "
            f"Unclosed cursor causes connection exhaustion and idle-in-transaction leaks. "
            f"Use 'with connection.cursor() as cursor:' to ensure clean closure."
        )
