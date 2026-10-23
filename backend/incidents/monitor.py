"""
Alert Monitor (FR-1.2).

Every few seconds: ask the database adapter how many connections are in use, store the
sample (for the live graph), and raise an alert when usage crosses the threshold
(default 90% of max_connections). Alerts go through the same ingest path as the
webhook, so duplicate suppression applies.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from telemetry import DatabaseAdapter, TelemetryUnavailable, get_adapter

from .models import RuntimeConfig, TelemetrySample
from .services import ingest_alert

logger = logging.getLogger("autosre.monitor")

KEEP_SAMPLES_FOR = timedelta(hours=2)


class AlertMonitor:
    def __init__(self, adapter: DatabaseAdapter | None = None, interval: float | None = None,
                 start_incidents: bool = True):
        self.adapter = adapter or get_adapter()
        self.interval = interval or settings.AUTOSRE["MONITOR_INTERVAL_SECONDS"]
        self.start_incidents = start_incidents
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._unreachable_logged = False
        self.last_error: str | None = None
        self.ticks = 0

    def tick(self) -> dict | None:
        """One sampling round. Returns the snapshot dict, or None if the DB is unreachable."""
        close_old_connections()
        config = RuntimeConfig.load()
        try:
            snap = self.adapter.snapshot()
        except TelemetryUnavailable as exc:
            self.last_error = str(exc)
            if not self._unreachable_logged:
                logger.warning("Monitor cannot read telemetry: %s", exc)
                self._unreachable_logged = True
            return None
        self._unreachable_logged = False
        self.last_error = None
        self.ticks += 1

        TelemetrySample.objects.create(
            active=snap.active, idle=snap.idle, idle_in_transaction=snap.idle_in_transaction,
            total=snap.total, max_connections=snap.max_connections,
        )
        if self.ticks % 100 == 0:
            TelemetrySample.objects.filter(ts__lt=timezone.now() - KEEP_SAMPLES_FOR).delete()

        if config.monitor_enabled and snap.utilization >= config.alert_threshold:
            ingest_alert(
                {
                    "source": "autosre-monitor",
                    "severity": "critical",
                    "metric": "pg_connections",
                    "value": snap.total,
                    "max": snap.max_connections,
                    "timestamp": snap.ts,
                },
                source="monitor",
                start=self.start_incidents,
            )
        return snap.as_dict()

    def run_forever(self) -> None:
        logger.info("Alert monitor started (every %.1fs)", self.interval)
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.tick()
            except Exception:  # never let the monitor die silently
                logger.exception("Monitor tick failed")
            self._stop.wait(max(0.0, self.interval - (time.monotonic() - started)))

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run_forever, name="autosre-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_monitor: AlertMonitor | None = None


def get_monitor() -> AlertMonitor | None:
    return _monitor


def start_monitor() -> AlertMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AlertMonitor()
        _monitor.start()
    return _monitor
