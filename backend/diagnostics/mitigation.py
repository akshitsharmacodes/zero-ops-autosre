"""
Stop the bleeding (AO-3): end the stuck sessions that belong to the application.

This restores service in seconds while the real fix is prepared. It does NOT fix the
cause — the leak will come back with new traffic until the code is fixed.

Safety (NFR-F4): this is the ONLY destructive action AutoSRE takes against the database,
and it is limited to sessions that (a) belong to the configured application, (b) are
idle in a transaction, and (c) have been stuck for at least `min_idle_seconds`.
"""
from __future__ import annotations

from telemetry import DatabaseAdapter, SessionInfo


def stop_the_bleeding(adapter: DatabaseAdapter, stuck: list[SessionInfo], app_prefix: str,
                      min_idle_seconds: int) -> dict:
    candidates = [s.pid for s in stuck if s.application_name.startswith(app_prefix)]
    skipped = len(stuck) - len(candidates)
    terminated = adapter.terminate(candidates, app_prefix, min_idle_seconds) if candidates else []
    after = adapter.snapshot()
    return {
        "action": "terminate idle-in-transaction sessions",
        "app_prefix": app_prefix,
        "candidates": len(candidates),
        "terminated": len(terminated),
        "terminated_pids": terminated[:200],
        "skipped_other_apps": skipped,
        "after": after.as_dict(),
    }
