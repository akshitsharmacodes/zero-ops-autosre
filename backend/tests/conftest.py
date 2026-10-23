import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


@pytest.fixture
def seeded_repo(tmp_path):
    """A fresh copy of the victim history: (origin bare repo, working clone)."""
    from seed_victim_repo import seed

    return seed(tmp_path / "victim")
