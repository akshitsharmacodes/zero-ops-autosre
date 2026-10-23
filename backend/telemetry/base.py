"""
Database adapters: one small "translator" per database engine.

The rest of AutoSRE only asks these questions, whatever the database is:
  * snapshot()        how many connections are in use, and in what state?
  * stuck_sessions()  which sessions are holding a transaction open and doing nothing?
  * terminate()       end these specific sessions (stop the bleeding)

Supporting MySQL later means writing one more adapter; nothing else changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


class TelemetryUnavailable(Exception):
    """The monitored database could not be reached or queried."""


@dataclass
class ConnectionSnapshot:
    active: int
    idle: int
    idle_in_transaction: int
    other: int
    max_connections: int
    by_application: dict[str, int] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total(self) -> int:
        return self.active + self.idle + self.idle_in_transaction + self.other

    @property
    def utilization(self) -> float:
        return self.total / self.max_connections if self.max_connections else 0.0

    def as_dict(self) -> dict:
        return {**asdict(self), "total": self.total, "utilization": round(self.utilization, 3)}


@dataclass
class SessionInfo:
    pid: int
    application_name: str
    user: str
    state: str
    state_age_seconds: float
    xact_age_seconds: float | None
    query: str

    def as_dict(self) -> dict:
        return asdict(self)


class DatabaseAdapter(ABC):
    engine: str = "unknown"

    @abstractmethod
    def snapshot(self) -> ConnectionSnapshot: ...

    @abstractmethod
    def stuck_sessions(self, min_idle_seconds: int, app_prefix: str | None = None) -> list[SessionInfo]: ...

    @abstractmethod
    def terminate(self, pids: list[int], app_prefix: str, min_idle_seconds: int) -> list[int]:
        """End only the given sessions, re-checking they still belong to the app and are still stuck."""

    def describe(self) -> dict:
        return {"engine": self.engine}
