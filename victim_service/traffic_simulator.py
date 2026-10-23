#!/usr/bin/env python3
"""
Load test: sends realistic HTTP traffic to the service.

Most requests hit the activity report (the busiest page in production), with some
health / metrics / top-pages traffic mixed in. It only talks HTTP — it never opens
database connections itself.
"""
import argparse
import random
import threading
import time
import urllib.error
import urllib.request

ROUTES = [
    ("/api/reports/user-activity/", 6),
    ("/api/reports/top-pages/", 1),
    ("/api/metrics/summary/", 1),
    ("/api/health/", 1),
]


def run(base_url, total, concurrency, delay, stop_event=None, on_result=None, seed=7):
    rng = random.Random(seed)
    paths = [p for p, weight in ROUTES for _ in range(weight)]
    plan = [rng.choice(paths) for _ in range(total)]
    stop_event = stop_event or threading.Event()
    lock = threading.Lock()
    counts = {"ok": 0, "error": 0}

    def worker():
        while not stop_event.is_set():
            with lock:
                if not plan:
                    return
                path = plan.pop()
            status = _get(base_url + path)
            with lock:
                counts["ok" if status == 200 else "error"] += 1
            if on_result:
                on_result(path, status)
            time.sleep(delay)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counts


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--requests", type=int, default=150)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()

    def show(path, status):
        print(f"{status} {path}")

    counts = run(args.base_url, args.requests, args.concurrency, args.delay, on_result=show)
    print(f"done: {counts}")


if __name__ == "__main__":
    main()
