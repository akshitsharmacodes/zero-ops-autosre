import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "scripts"))  # after backend/, so scripts/demo.py never shadows backend/demo


@pytest.fixture
def seeded_repo(tmp_path):
    """A fresh copy of the victim history: (origin bare repo, working clone)."""
    from seed_victim_repo import seed

    return seed(tmp_path / "victim")


from .test_pipeline import env  # noqa: E402,F401  (shared end-to-end fixture)
