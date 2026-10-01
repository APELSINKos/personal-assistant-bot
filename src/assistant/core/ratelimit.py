"""Per-user sliding-window rate limit, kept in the memory of the process that checks it (the
API's single worker, or the bot)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._hits: dict[int, deque[float]] = {}

    def check(self, key: int) -> float | None:
        """Count one request; None when it is allowed, otherwise the seconds to wait."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return hits[0] + self._window - now
        hits.append(now)
        return None
