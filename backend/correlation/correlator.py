"""
Find the commit that most likely caused the incident (FR-3.x).

How it works, in plain words:
  1. Take the recent commits (last 20, plus anything from the last 7 days).
  2. For every file each commit changed, look only at the lines it ADDED.
  3. Score those added lines against the clues from the diagnosis:
       - the stuck SQL query's distinctive words (table and column names)   strongest clue
       - the function/view that served the failing URL
       - the failing URL itself (e.g. "reports/user-activity/")
       - source files that appear in error stack traces
       - loggers that were warning
  4. The best-scoring commit is the suspect. Confidence is high when it clearly beats
     the runner-up.
  5. Inside the suspect file, find the exact function/lines and confirm with
     `git blame` that those lines really came from the suspect commit.

Language-neutral: everything is text matching on diffs. Python files get an extra
precise step (exact function boundaries via the `ast` module).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workspace.gitcmd import FileDiff, GitError, git, parse_unified_diff

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
SQL_STOPWORDS = {
    "select", "from", "where", "group", "order", "by", "limit", "desc", "asc", "as", "and", "or",
    "not", "null", "count", "max", "min", "sum", "avg", "join", "left", "right", "inner", "outer",
    "on", "in", "is", "set", "update", "insert", "into", "values", "having", "distinct", "case",
    "when", "then", "else", "end", "true", "false", "with", "begin", "commit", "rollback", "now",
    "current_timestamp", "offset", "like", "between", "exists", "union", "all",
}
WEIGHTS = {"query": 0.45, "function": 0.25, "endpoint": 0.15, "frame": 0.10, "logger": 0.05}
MIN_SCORE = 0.15


class CorrelationFailed(Exception):
    pass


@dataclass
class Clues:
    query_tokens: set[str]
    endpoint_fragments: list[str]
    function_names: set[str]
    frame_files: list[tuple[str, int, str]]  # (path suffix, line, function)
    logger_paths: set[str]

    @classmethod
    def from_evidence(cls, evidence: dict) -> "Clues":
        tokens: set[str] = set()
        for q in evidence.get("queries", []):
            tokens |= {t.lower() for t in IDENT_RE.findall(q) if t.lower() not in SQL_STOPWORDS}

        fragments = []
        for ep in evidence.get("endpoints", []):
            parts = [p for p in ep.strip("/").split("/") if p]
            # "api/reports/user-activity" -> "reports/user-activity", "user-activity"
            for i in range(1, len(parts)):
                fragments.append("/".join(parts[i:]))
        functions = {v.rsplit(".", 1)[-1] for v in evidence.get("views", []) if v}
        frames = []
        for f in evidence.get("frames", []):
            frames.append((_path_suffix(f["file"]), int(f.get("line", 0)), f.get("function", "")))
            functions.add(f.get("function", ""))
        functions.discard("")
        loggers = {name.replace(".", "/") for name in evidence.get("loggers", []) if "." in name}
        return cls(tokens, sorted(set(fragments), key=len, reverse=True), functions, frames, loggers)


def _path_suffix(path: str) -> str:
    p = path.replace("\\", "/")
    for marker in ("/app/", "/work/", "/src/"):
        if marker in p:
            p = p.split(marker, 1)[1]
    return p.lstrip("/")


@dataclass
class FileScore:
    path: str
    score: float
    reasons: list[str]
    query_hits: set[str]
    best_line: int | None


def score_file(fd: FileDiff, clues: Clues) -> FileScore:
    added_text = "\n".join(text for _, text in fd.added)
    added_tokens = {t.lower() for t in IDENT_RE.findall(added_text)}
    score, reasons = 0.0, []

    hits = clues.query_tokens & added_tokens
    if clues.query_tokens and hits:
        frac = len(hits) / len(clues.query_tokens)
        score += WEIGHTS["query"] * frac
        reasons.append(f"added lines contain {len(hits)}/{len(clues.query_tokens)} distinctive words of the stuck query "
                       f"({', '.join(sorted(hits)[:6])})")

    defined = {name for name in clues.function_names
               if re.search(rf"\b(def|function|func|fn)\s+{re.escape(name)}\b", added_text)}
    if defined:
        score += WEIGHTS["function"]
        reasons.append(f"defines {', '.join(sorted(defined))}, which served the failing requests")

    for frag in clues.endpoint_fragments:
        if frag in added_text:
            score += WEIGHTS["endpoint"] * (0.5 if "/" not in frag else 1.0)
            reasons.append(f"adds the route '{frag}' that appears in failing requests")
            break

    for suffix, line, func in clues.frame_files:
        if suffix and (fd.path.endswith(suffix) or suffix.endswith(fd.path)):
            in_added = any(abs(n - line) <= 2 for n, _ in fd.added)
            score += WEIGHTS["frame"] * (1.0 if in_added else 0.4)
            reasons.append(f"file appears in error stack traces ({suffix}:{line} in {func})")
            break

    if any(fd.path.startswith(lp) or fd.path.removesuffix(Path(fd.path).suffix) == lp for lp in clues.logger_paths):
        score += WEIGHTS["logger"]
        reasons.append("module's logger was emitting warnings")

    best_line = None
    if hits:
        best_line = max(fd.added, key=lambda item: len(hits & {t.lower() for t in IDENT_RE.findall(item[1])}))[0]
    elif defined:
        best_line = next((n for n, t in fd.added if any(f in t for f in defined)), None)
    return FileScore(fd.path, round(score, 3), reasons, hits, best_line)


class GitCorrelator:
    def __init__(self, repo_path: str | Path, base_branch: str = "main",
                 lookback_commits: int = 20, lookback_days: int = 7):
        self.repo = Path(repo_path)
        self.base_branch = base_branch
        self.lookback_commits = lookback_commits
        self.lookback_days = lookback_days

    def refresh(self) -> str:
        """Update the working clone from origin (if it has one) and return the ref to analyze."""
        remotes = git("remote", cwd=self.repo).split()
        if "origin" in remotes:
            git("fetch", "--quiet", "origin", self.base_branch, cwd=self.repo, timeout=60)
            return f"origin/{self.base_branch}"
        return self.base_branch

    def recent_commits(self, ref: str) -> list[dict]:
        out = git("log", ref, "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s", "-n", "200", cwd=self.repo)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        commits = []
        for i, line in enumerate(out.splitlines()):
            sha, name, email, date, subject = line.split("\x1f")
            when = datetime.fromisoformat(date)
            if i >= self.lookback_commits and when < cutoff:
                break
            commits.append({"sha": sha, "short_sha": sha[:8], "author": name, "email": email,
                            "date": date, "message": subject})
        return commits

    def correlate(self, evidence: dict) -> dict:
        try:
            ref = self.refresh()
            base_sha = git("rev-parse", ref, cwd=self.repo).strip()
            commits = self.recent_commits(ref)
        except GitError as exc:
            raise CorrelationFailed(f"cannot read git history: {exc}") from exc
        if not commits:
            raise CorrelationFailed("repository has no commits to analyze")

        clues = Clues.from_evidence(evidence)
        ranked = []
        for c in commits:
            diff = git("show", c["sha"], "--format=", "--unified=0", "--no-color", "--no-renames", cwd=self.repo)
            file_scores = [score_file(fd, clues) for fd in parse_unified_diff(diff).values() if not fd.is_deleted]
            if not file_scores:
                continue
            file_scores.sort(key=lambda fs: fs.score, reverse=True)
            best = file_scores[0]
            total = best.score + 0.1 * sum(fs.score for fs in file_scores[1:])
            ranked.append((min(total, 1.0), c, file_scores))

        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0] < MIN_SCORE:
            raise CorrelationFailed("no recent commit matches the incident evidence strongly enough")

        top_score, commit, file_scores = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = (top_score - runner_up) / top_score if top_score else 0.0
        confidence = round(min(0.99, top_score * (0.6 + 0.4 * margin) + 0.25 * margin), 2)

        primary = file_scores[0]
        location = self.locate(ref, primary, commit["sha"])
        changed_files = [fs.path for fs in file_scores]
        commit_diff = git("show", commit["sha"], "--format=", "--no-color", cwd=self.repo)

        reasons = list(primary.reasons)
        for fs in file_scores[1:]:
            reasons += [f"{fs.path}: {r}" for r in fs.reasons]
        if location.get("blame_ratio") is not None:
            reasons.append(f"git blame: {location['blame_ratio']:.0%} of the leaking lines come from this commit")

        return {
            "commit": commit,
            "base_ref": ref,
            "base_sha": base_sha,
            "files": changed_files,
            "primary_file": primary.path,
            "location": location,
            "score": round(top_score, 3),
            "confidence": confidence,
            "evidence": reasons,
            "candidates": [
                {"sha": c["short_sha"], "author": c["author"], "message": c["message"], "score": round(s, 3)}
                for s, c, _ in ranked[:5]
            ],
            "commit_diff": commit_diff,
        }

    # -- exact location -----------------------------------------------------------
    def locate(self, ref: str, fs: FileScore, sha: str) -> dict:
        try:
            source = git("show", f"{ref}:{fs.path}", cwd=self.repo)
        except GitError:
            return {"file": fs.path}
        lines = source.splitlines()
        start, end, function = None, None, None

        if fs.path.endswith(".py"):
            start, end, function = _python_function_around(source, fs.best_line, fs.query_hits)
        if start is None and fs.best_line:
            start, end = max(1, fs.best_line - 8), min(len(lines), fs.best_line + 8)
        if start is None:
            return {"file": fs.path}

        snippet = "\n".join(lines[start - 1:end])
        blame_ratio = self._blame_ratio(ref, fs.path, start, end, sha)
        return {"file": fs.path, "function": function, "start_line": start, "end_line": end,
                "snippet": snippet, "blame_ratio": blame_ratio}

    def _blame_ratio(self, ref: str, path: str, start: int, end: int, sha: str) -> float | None:
        try:
            out = git("blame", "--porcelain", "-L", f"{start},{end}", ref, "--", path, cwd=self.repo)
        except GitError:
            return None
        owners = [line.split()[0] for line in out.splitlines() if re.match(r"^[0-9a-f]{40} \d+ \d+", line)]
        return round(sum(1 for o in owners if o == sha) / len(owners), 2) if owners else None


def _python_function_around(source: str, line: int | None, hits: set[str]):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, None, None
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if line:
        containing = [f for f in funcs if f.lineno <= line <= (f.end_lineno or f.lineno)]
        if containing:
            f = min(containing, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
            return f.lineno, f.end_lineno, f.name
    if hits:
        lines = source.splitlines()

        def overlap(f):
            body = "\n".join(lines[f.lineno - 1:f.end_lineno]).lower()
            return sum(1 for h in hits if h in body)

        best = max(funcs, key=overlap, default=None)
        if best and overlap(best):
            return best.lineno, best.end_lineno, best.name
    return None, None, None
