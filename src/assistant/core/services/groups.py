"""The MIREA group directory.

`english.mirea.ru` serves every group's calendar by number but has no search, so the bot
reads the first bytes of each calendar (its header names the group and the semester's end)
and keeps the groups whose semester is still on. A full crawl walks every number; a quick one
only the newest numbers, where new groups appear.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.clients.calendars import Calendars
from assistant.core.errors import InvalidInput
from assistant.core.models import JobRun, MireaGroup
from assistant.core.services.group_names import (
    MIREA_ZONE,
    GroupHeader,
    name_key,
    read_header,
    search_keys,
)
from assistant.core.timeutil import local_today, utcnow

log = logging.getLogger(__name__)

MIREA_URL = "https://english.mirea.ru/schedule/api/ical/1/{}"
SEARCH_LIMIT = 10
HEAD_BYTES = 4096
PACE = 1 / 3  # seconds between request starts: at most three requests a second
FIRST_UPPER = 6000  # a full crawl tries at least this far, whatever it finds
BEYOND_LAST = 300  # numbers tried past the highest group found
QUICK_BEHIND = 50  # a quick crawl also re-reads this many numbers below the highest known one
PRUNE_MIN_FOUND = 100  # a full crawl that found fewer (MIREA was down) removes nothing
# A crawl cannot tell a group that is gone from a request that failed (a timeout, a rate limit,
# a challenge page), so a group goes only when no crawl has seen it for longer than two weekly
# full crawls. Search hides ended semesters anyway: removing is only garbage collection.
PRUNE_AFTER = timedelta(days=15)
FULL_JOB = "mirea_full"
QUICK_JOB = "mirea_quick"

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CrawlResult:
    checked: int
    found: int
    highest: int  # the highest number with a current group; 0 when none was found


def calendar_url(group_id: int) -> str:
    return MIREA_URL.format(group_id)


async def get(session: AsyncSession, group_id: int) -> MireaGroup | None:
    return await session.get(MireaGroup, group_id)


async def count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(MireaGroup)) or 0)


async def max_id(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.max(MireaGroup.id))) or 0)


async def search(
    session: AsyncSession, query: str, today: date | None = None, limit: int = SEARCH_LIMIT
) -> list[MireaGroup]:
    """Groups whose name contains the query; names that start with it come first."""
    keys = search_keys(query)
    if not keys:
        return []
    current = today or local_today(MIREA_ZONE)
    rows = (
        await session.scalars(
            select(MireaGroup).where(
                MireaGroup.semester_end >= current,
                or_(*(MireaGroup.name_key.contains(key, autoescape=True) for key in keys)),
            )
        )
    ).all()

    def rank(group: MireaGroup) -> tuple[bool, str]:
        return (not any(group.name_key.startswith(key) for key in keys), group.name)

    return sorted(rows, key=rank)[:limit]


async def remember(
    session: AsyncSession, group_id: int, header: GroupHeader, now: datetime
) -> None:
    if header.semester_end is None:
        raise ValueError("only a group with a timetable is remembered")
    values = {
        "name": header.name,
        "name_key": name_key(header.name),
        "semester_end": header.semester_end,
        "seen_at": now,
    }
    statement = insert(MireaGroup).values(id=group_id, **values)
    await session.execute(
        statement.on_conflict_do_update(index_elements=[MireaGroup.id], set_=values)
    )


async def prune(session: AsyncSession, seen_before: datetime) -> int:
    result = await session.execute(delete(MireaGroup).where(MireaGroup.seen_at < seen_before))
    return int(result.rowcount)  # type: ignore[attr-defined]


async def last_run(session: AsyncSession, name: str) -> datetime | None:
    run = await session.get(JobRun, name)
    return None if run is None else run.finished_at


async def record_run(session: AsyncSession, name: str, finished_at: datetime, info: str) -> None:
    run = await session.get(JobRun, name)
    if run is None:
        session.add(JobRun(name=name, finished_at=finished_at, info=info))
    else:
        run.finished_at, run.info = finished_at, info
    await session.flush()


async def building(session: AsyncSession) -> bool:
    """Whether the directory is still being built: no full crawl has finished yet."""
    return await last_run(session, FULL_JOB) is None


async def crawl(
    sessionmaker: async_sessionmaker[AsyncSession],
    calendars: Calendars,
    first: int,
    upper: int,
    *,
    now: Clock = utcnow,
    stop: asyncio.Event | None = None,
    sleep: Sleep = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> CrawlResult:
    """Read numbers first…upper (the upper end moves along past every group found) and
    remember the groups whose semester has not ended. Each group is written in its own short
    transaction: a crawl takes half an hour and must never hold SQLite's write lock."""
    checked = found = highest = 0
    group_id = first
    started: float | None = None
    while group_id <= upper and not (stop is not None and stop.is_set()):
        if started is not None:
            wait = PACE - (monotonic() - started)
            if wait > 0:
                await sleep(wait)
        started = monotonic()
        checked += 1
        try:
            head = await calendars.head(calendar_url(group_id), HEAD_BYTES)
        except InvalidInput:  # 404 for a number nobody has, a timeout, a network error
            head = b""
        header = read_header(head)
        moment = now()
        if (
            header is not None
            and header.semester_end is not None
            and header.semester_end >= local_today(MIREA_ZONE, moment)
        ):
            async with sessionmaker() as session:
                await remember(session, group_id, header, moment)
                await session.commit()
            found += 1
            highest = group_id
            upper = max(upper, group_id + BEYOND_LAST)
        group_id += 1
    return CrawlResult(checked, found, highest)


async def full_crawl(
    sessionmaker: async_sessionmaker[AsyncSession],
    calendars: Calendars,
    *,
    now: Clock = utcnow,
    stop: asyncio.Event | None = None,
    sleep: Sleep = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> CrawlResult:
    """Every number from 1. Then the groups no crawl has seen for PRUNE_AFTER are removed — but
    only when this crawl found a sane number of groups: a crawl during a MIREA outage must not
    empty the directory, and one cut short half-way must not drop the groups it failed to read."""
    started = now()
    async with sessionmaker() as session:
        top = await max_id(session)
    result = await crawl(
        sessionmaker,
        calendars,
        1,
        max(FIRST_UPPER, top + BEYOND_LAST),
        now=now,
        stop=stop,
        sleep=sleep,
        monotonic=monotonic,
    )
    if stop is not None and stop.is_set():
        return result  # interrupted by a shutdown: not a finished crawl, nothing is removed
    async with sessionmaker() as session:
        healthy = result.found >= PRUNE_MIN_FOUND
        removed = await prune(session, started - PRUNE_AFTER) if healthy else 0
        info = f"checked {result.checked}, found {result.found}, removed {removed}"
        await record_run(session, FULL_JOB, now(), info)
        await session.commit()
    log.info("MIREA directory, full crawl: %s", info)
    return result


async def quick_crawl(
    sessionmaker: async_sessionmaker[AsyncSession],
    calendars: Calendars,
    *,
    now: Clock = utcnow,
    stop: asyncio.Event | None = None,
    sleep: Sleep = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> CrawlResult:
    """Only the newest numbers, where groups of a new intake appear."""
    async with sessionmaker() as session:
        top = await max_id(session)
    if top == 0:
        return CrawlResult(0, 0, 0)  # nothing known yet: the full crawl comes first
    result = await crawl(
        sessionmaker,
        calendars,
        max(1, top - QUICK_BEHIND),
        top + BEYOND_LAST,
        now=now,
        stop=stop,
        sleep=sleep,
        monotonic=monotonic,
    )
    if stop is not None and stop.is_set():
        return result
    async with sessionmaker() as session:
        info = f"checked {result.checked}, found {result.found}"
        await record_run(session, QUICK_JOB, now(), info)
        await session.commit()
    log.info("MIREA directory, quick crawl: %s", info)
    return result
