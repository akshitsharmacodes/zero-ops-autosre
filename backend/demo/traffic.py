"""
Demo traffic driver: sends HTTP requests to the victim service (never opens DB
connections itself). The leak happens inside the victim app; the Alert Monitor then
notices the saturation and opens the incident on its own (acceptance criterion 2).
"""
from __future__ import annotations

import random
import threading
import time
import urllib.error
import urllib.request

ROUTES = [("/api/reports/user-activity/", 6), ("/api/reports/top-pages/", 1),
          ("/api/metrics/summary/", 1), ("/api/health/", 1)]


class TrafficDriver:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.stats = {"sent": 0, "ok": 0, "errors": 0, "running": False, "started_at": None, "target": 0}

    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def start(self, base_url: str, total: int = 400, concurrency: int = 8, delay: float = 0.05, seed: int = 7) -> dict:
        if self.running():
            return self.status()
        rng = random.Random(seed)
        paths = [p for p, w in ROUTES for _ in range(w)]
        plan = [rng.choice(paths) for _ in range(total)]
        self._stop.clear()
        self.stats = {"sent": 0, "ok": 0, "errors": 0, "running": True, "started_at": time.time(), "target": total}

        def worker():
            while not self._stop.is_set():
                with self._lock:
                    if not plan:
                        return
                    path = plan.pop()
                status = _get(base_url.rstrip("/") + path)
                with self._lock:
                    self.stats["sent"] += 1
                    self.stats["ok" if status == 200 else "errors"] += 1
                time.sleep(delay)

        self._threads = [threading.Thread(target=worker, daemon=True, name=f"traffic-{i}") for i in range(concurrency)]
        for t in self._threads:
            t.start()
        return self.status()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {**self.stats, "running": self.running()}


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def victim_reachable(base_url: str) -> bool:
    return _get(base_url.rstrip("/") + "/api/health/") == 200


driver = TrafficDriver()
