"""
Client-side rate limiting: stay under the provider's tokens-per-minute cap instead of
crashing into it. Thread-safe, so concurrent incidents share one budget per provider.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class RollingTokenLimiter:
    """Allows at most `tokens_per_minute` tokens in any rolling 60-second window."""

    WINDOW_SECONDS = 60.0

    def __init__(self, tokens_per_minute: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.limit = tokens_per_minute
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def used(self) -> int:
        with self._lock:
            self._expire()
            return sum(n for _, n in self._events)

    def acquire(self, tokens: int) -> float:
        """Block until `tokens` fit in the window, then reserve them. Returns seconds waited."""
        if not self.enabled:
            return 0.0
        tokens = min(tokens, self.limit)  # a single request can never need more than the full window
        waited = 0.0
        while True:
            with self._lock:
                self._expire()
                in_window = sum(n for _, n in self._events)
                if in_window + tokens <= self.limit:
                    self._events.append((self._clock(), tokens))
                    return waited
                wait = self._events[0][0] + self.WINDOW_SECONDS - self._clock() + 0.05
            wait = max(wait, 0.05)
            self._sleep(wait)
            waited += wait

    def adjust_last(self, actual_tokens: int) -> None:
        """Replace the last reservation with the real usage reported by the API."""
        with self._lock:
            if self._events:
                ts, _ = self._events.pop()
                self._events.append((ts, actual_tokens))

    def _expire(self) -> None:
        cutoff = self._clock() - self.WINDOW_SECONDS
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()


_shared: dict[str, RollingTokenLimiter] = {}
_shared_lock = threading.Lock()


def shared_limiter(key: str, tokens_per_minute: int) -> RollingTokenLimiter:
    """One limiter per provider/model, shared by all agents in this process."""
    with _shared_lock:
        limiter = _shared.get(key)
        if limiter is None or limiter.limit != tokens_per_minute:
            limiter = _shared[key] = RollingTokenLimiter(tokens_per_minute)
        return limiter
