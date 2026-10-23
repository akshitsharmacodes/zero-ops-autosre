"""
Turn raw clues into a structured diagnosis (FR-2.4).

Input: a connection snapshot, the stuck sessions, the log summary and (optionally) a
healthy baseline. Output: a dict that is stored on the incident, shown on the dashboard,
and handed to the correlation step and the coding agent.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from telemetry import ConnectionSnapshot, SessionInfo

from .logs import LogSummary

WHITESPACE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Collapse whitespace and replace literal values so identical queries group together."""
    q = WHITESPACE.sub(" ", query or "").strip()
    q = re.sub(r"'[^']*'", "?", q)
    q = re.sub(r"\b\d+\b", "?", q)
    return q


def group_sessions(sessions: list[SessionInfo]) -> list[dict]:
    groups: dict[tuple[str, str], list[SessionInfo]] = defaultdict(list)
    for s in sessions:
        groups[(s.application_name, normalize_query(s.query))].append(s)
    result = []
    for (app, query), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        result.append({
            "application_name": app,
            "query": query,
            "example_query": items[0].query,
            "count": len(items),
            "max_idle_seconds": max(s.state_age_seconds for s in items),
            "pids": [s.pid for s in items],
        })
    return result


def build_diagnosis(
    snapshot: ConnectionSnapshot,
    stuck: list[SessionInfo],
    logs: LogSummary,
    baseline: dict | None = None,
    threshold: float = 0.9,
) -> dict:
    groups = group_sessions(stuck)
    top = groups[0] if groups else None
    snap = snapshot.as_dict()

    delta = None
    if baseline and baseline.get("total") is not None:
        delta = {
            key: snap[key] - round(baseline.get(key, 0))
            for key in ("total", "active", "idle", "idle_in_transaction")
        }

    findings = []
    if snapshot.utilization >= threshold:
        findings.append(
            f"Connection usage is {snapshot.total}/{snapshot.max_connections} "
            f"({snapshot.utilization:.0%}), above the {threshold:.0%} alert threshold."
        )
    if top:
        findings.append(
            f"{len(stuck)} session(s) are idle in transaction; the largest group is {top['count']} from "
            f"'{top['application_name'] or 'unnamed app'}' stuck up to {top['max_idle_seconds']:.0f}s after running: "
            f"{top['query'][:160]}"
        )
    if logs.errors.get("connection_exhaustion"):
        findings.append(f"Application logs show {logs.errors['connection_exhaustion']} 'too many clients' style errors.")
    if logs.warning_loggers:
        name, count = logs.warning_loggers[0]
        findings.append(f"Logger '{name}' emitted {count} warning/error line(s).")

    leak_suspected = bool(top) and (top["count"] >= 3 or snapshot.idle_in_transaction >= 0.3 * snapshot.max_connections)
    hypothesis = (
        "Connection leak: application code opens a database transaction/connection and never "
        "releases it, so sessions pile up 'idle in transaction' until the server refuses new clients."
        if leak_suspected
        else "Connection saturation without a clear leak signature (could be a traffic spike)."
    )

    endpoint_counts: Counter = Counter()
    for path, n in logs.busiest_paths:
        endpoint_counts[path] += n

    return {
        "snapshot": snap,
        "baseline": baseline,
        "delta": delta,
        "stuck_sessions": {"count": len(stuck), "groups": groups[:5]},
        "logs": logs.as_dict(),
        "findings": findings,
        "hypothesis": hypothesis,
        "leak_suspected": leak_suspected,
        # Compact evidence handed to correlation + the coding agent.
        "evidence": {
            "queries": [g["example_query"] for g in groups[:3]],
            "application_names": sorted({g["application_name"] for g in groups if g["application_name"]}),
            "endpoints": [p for p, _ in logs.failing_paths] + [p for p, _ in endpoint_counts.most_common(3)],
            "views": [v for v, _ in logs.views],
            "loggers": [name for name, _ in logs.warning_loggers],
            "frames": logs.frames[:5],
        },
    }
