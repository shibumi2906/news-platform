"""Bounded in-memory limiter for local authentication endpoints."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from time import monotonic


class SlidingWindowLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = float("-inf")

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            if current - self._last_cleanup >= self.window_seconds:
                stale_keys = [
                    item_key
                    for item_key, item_events in self._events.items()
                    if not item_events or item_events[-1] <= cutoff
                ]
                for item_key in stale_keys:
                    self._events.pop(item_key, None)
                self._last_cleanup = current
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(current)
            return True
