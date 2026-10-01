"""Keeps the MIREA group directory fresh from inside the bot process.

A full crawl runs at the very first start (group search needs it the same day) and then once a
week; a quick one, over the newest numbers only, once a day. Both run at night in Moscow, when
the timetable site is quiet, and at most three requests a second (services/groups.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.clients.calendars import Calendars
from assistant.core.services import groups
from assistant.core.services.group_names import MIREA_ZONE
from assistant.core.timeutil import to_local, utcnow

log = logging.getLogger(__name__)

FULL_EVERY = timedelta(days=7)
RETRY_EVERY = timedelta(days=1)  # a full crawl that left too few groups is retried sooner
QUICK_EVERY = timedelta(days=1)
NIGHT_HOURS = range(1, 5)  # 01:00–04:59 in Moscow
CHECK_EVERY = 600.0  # seconds between checks whether a crawl is due


class DirectoryCrawler:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        calendars: Calendars,
        *,
        clock: Callable[[], datetime] = utcnow,
        check_every: float = CHECK_EVERY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._calendars = calendars
        self._clock = clock
        self._check_every = check_every
        self._sleep = sleep
        self._monotonic = monotonic
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        log.info("MIREA directory crawler started")
        while not self._stopping.is_set():
            try:
                await self.step()
            except Exception:
                log.exception("MIREA directory crawl failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._check_every)
        log.info("MIREA directory crawler stopped")

    def stop(self) -> None:
        """Stop between two requests; a crawl cut short is not recorded as finished."""
        self._stopping.set()

    async def due(self) -> str | None:
        """Which crawl should run now: "full", "quick" or none."""
        now = self._clock()
        async with self._sessionmaker() as session:
            full_at = await groups.last_run(session, groups.FULL_JOB)
            quick_at = await groups.last_run(session, groups.QUICK_JOB)
            known = await groups.count(session)
        if full_at is None:
            return "full"  # the first start: group search is needed today, not tonight
        if to_local(now, MIREA_ZONE).hour not in NIGHT_HOURS:
            return None
        if now - full_at >= (FULL_EVERY if known >= groups.PRUNE_MIN_FOUND else RETRY_EVERY):
            return "full"
        if now - max(full_at, quick_at or full_at) >= QUICK_EVERY:
            return "quick"
        return None

    async def step(self) -> str | None:
        kind = await self.due()
        if kind == "full":
            await groups.full_crawl(
                self._sessionmaker,
                self._calendars,
                now=self._clock,
                stop=self._stopping,
                sleep=self._sleep,
                monotonic=self._monotonic,
            )
        elif kind == "quick":
            await groups.quick_crawl(
                self._sessionmaker,
                self._calendars,
                now=self._clock,
                stop=self._stopping,
                sleep=self._sleep,
                monotonic=self._monotonic,
            )
        return kind
