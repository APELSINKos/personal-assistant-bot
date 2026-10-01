"""Everything a request handler needs from the running application."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from weakref import WeakValueDictionary

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings
from assistant.core.ratelimit import RateLimiter


@dataclass
class AppState:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    meteo: OpenMeteoClient
    cbr: CbrClient
    calendars: Calendars
    limiter: RateLimiter
    attempts: RateLimiter  # schedule.attempt_limiter: the downloads and parses users start
    clock: Callable[[], datetime]
    commit: str | None
    # A lock is kept only while a request holds or awaits it.
    _schedule_locks: WeakValueDictionary[int, asyncio.Lock] = field(
        default_factory=WeakValueDictionary, init=False, repr=False
    )

    def schedule_lock(self, user_id: int) -> asyncio.Lock:
        """The user's schedule changes go one at a time (the API is one process): a second
        click on «refresh» must find the first one's result, a connect must not land in the
        middle of a refresh."""
        lock = self._schedule_locks.get(user_id)
        if lock is None:
            lock = self._schedule_locks[user_id] = asyncio.Lock()
        return lock
