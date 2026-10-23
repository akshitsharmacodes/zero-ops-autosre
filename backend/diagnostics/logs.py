"""
Application log reader.

Reads the tail of the app's log file and pulls out the clues that matter for a
connection incident: database errors, which URLs/views were busy or failing, which
loggers were warning, and which source-code lines appear in stack traces.

Works with JSON lines (preferred, VS-6) and falls back to plain text lines.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ERROR_PATTERNS = {
    "connection_exhaustion": re.compile(
        r"too many clients|remaining connection slots are reserved|connection limit exceeded", re.I
    ),
    "connect_failure": re.compile(r"could not connect|connection refused|server closed the connection", re.I),
    "timeout": re.compile(r"timed? ?out|statement timeout|canceling statement", re.I),
}

FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>[\w<>]+)')
# Library code is not interesting for "which of OUR files is involved".
LIBRARY_HINTS = ("site-packages", "dist-packages", "/lib/python", "\\lib\\python", "<frozen")

MAX_TAIL_BYTES = 2_000_000


@dataclass
class LogSummary:
    path: str
    readable: bool = True
    lines_scanned: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    failing_paths: list[tuple[str, int]] = field(default_factory=list)
    busiest_paths: list[tuple[str, int]] = field(default_factory=list)
    views: list[tuple[str, int]] = field(default_factory=list)
    warning_loggers: list[tuple[str, int]] = field(default_factory=list)
    frames: list[dict] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def read_tail(path: Path, max_bytes: int = MAX_TAIL_BYTES) -> list[str]:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            fh.readline()  # drop the partial first line
        return fh.read().decode("utf-8", errors="replace").splitlines()


def parse_lines(lines: list[str], path: str = "") -> LogSummary:
    summary = LogSummary(path=path, lines_scanned=len(lines))
    errors: Counter = Counter()
    failing: Counter = Counter()
    busiest: Counter = Counter()
    views: Counter = Counter()
    warners: Counter = Counter()
    frames: Counter = Counter()
    samples: list[str] = []

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        record = _as_record(raw)
        text = " ".join(str(record.get(k, "")) for k in ("msg", "exc", "error")) or raw
        level = str(record.get("level", "")).upper()

        req_path = record.get("path")
        status = record.get("status")
        if req_path:
            busiest[req_path] += 1
            if isinstance(status, int) and status >= 500:
                failing[req_path] += 1
        if record.get("view"):
            views[record["view"]] += 1
        if level in ("WARNING", "ERROR", "CRITICAL") and record.get("logger"):
            warners[record["logger"]] += 1

        matched = False
        for kind, pattern in ERROR_PATTERNS.items():
            if pattern.search(text):
                errors[kind] += 1
                matched = True
        if matched or level in ("ERROR", "CRITICAL"):
            for m in FRAME_RE.finditer(text):
                if not any(h in m["file"] for h in LIBRARY_HINTS):
                    frames[(m["file"], int(m["line"]), m["func"])] += 1
            if len(samples) < 8:
                samples.append(raw[:600])

    summary.errors = dict(errors)
    summary.failing_paths = failing.most_common(5)
    summary.busiest_paths = busiest.most_common(5)
    summary.views = views.most_common(5)
    summary.warning_loggers = warners.most_common(5)
    summary.frames = [
        {"file": f, "line": line, "function": func, "count": n} for (f, line, func), n in frames.most_common(10)
    ]
    summary.samples = samples
    return summary


def summarize_log_file(path: str | Path) -> LogSummary:
    p = Path(path)
    if not p.exists():
        return LogSummary(path=str(p), readable=False, note="log file not found")
    try:
        return parse_lines(read_tail(p), str(p))
    except OSError as exc:
        return LogSummary(path=str(p), readable=False, note=f"cannot read log file: {exc}")


def _as_record(raw: str) -> dict:
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return {"msg": raw}
