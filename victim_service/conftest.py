import pytest

from analytics.pool import report_pool
from tests.fakes import FakeConnection


@pytest.fixture(autouse=True)
def fake_report_pool():
    """The reporting pool hands out in-memory connections during tests."""
    report_pool.reset(connect=FakeConnection)
    yield report_pool
    report_pool.reset()
