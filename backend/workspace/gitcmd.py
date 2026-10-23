"""Thin, timeout-guarded wrapper around the git CLI plus a unified-diff parser."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class GitError(RuntimeError):
    pass


# Never let git open an editor or ask for credentials interactively.
_GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "true",
    "GIT_MERGE_AUTOEDIT": "no",
    "LC_ALL": "C",
}


def git(*args: str, cwd: str | Path, timeout: int = 60, env: dict | None = None, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "core.quotepath=off", *args],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env={**os.environ, **_GIT_ENV, **(env or {})},
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    added: list[tuple[int, str]] = field(default_factory=list)  # (new line number, text)
    removed: list[str] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False

    @property
    def changed_lines(self) -> int:
        return len(self.added) + len(self.removed)


def parse_unified_diff(diff_text: str) -> dict[str, FileDiff]:
    files: dict[str, FileDiff] = {}
    current: FileDiff | None = None
    new_line = 0
    old_path = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            current, old_path = None, None
            continue
        if line.startswith("--- "):
            old_path = line[4:].strip()
            continue
        if line.startswith("+++ "):
            new_path = line[4:].strip()
            deleted = new_path == "/dev/null"
            path = (old_path if deleted else new_path)
            path = path[2:] if path.startswith(("a/", "b/")) else path
            current = files.setdefault(path, FileDiff(path=path))
            current.is_new = old_path == "/dev/null"
            current.is_deleted = deleted
            continue
        m = HUNK_RE.match(line)
        if m:
            new_line = int(m.group(3))
            continue
        if current is None:
            continue
        if line.startswith("+"):
            current.added.append((new_line, line[1:]))
            new_line += 1
        elif line.startswith("-"):
            current.removed.append(line[1:])
        elif line.startswith(" "):
            new_line += 1
    return files
