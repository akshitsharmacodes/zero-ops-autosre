"""CodeBriefing packs the suspect file + its local imports into the agent's task."""
from agent.coding.briefing import CodeBriefing
from workspace.workspace import Workspace


def test_briefing_includes_suspect_file_and_local_imports(seeded_repo, tmp_path):
    origin, _ = seeded_repo
    ws = Workspace.create(str(origin), "main", "autosre/fix-brief", parent_dir=tmp_path / "ws")
    try:
        files = dict(CodeBriefing(ws).build("analytics/views.py"))
        assert list(files)[0] == "analytics/views.py"
        assert {"analytics/pool.py", "analytics/models.py"} <= set(files)       # from .pool / from .models
        assert "   3 | from .models import UserActivity" in files["analytics/views.py"]
        small = CodeBriefing(ws, max_chars=300).build("analytics/views.py")
        assert len(small) == 1 and "truncated" in small[0][1]
        assert CodeBriefing(ws).build("does/not/exist.py") == []
    finally:
        ws.cleanup()
