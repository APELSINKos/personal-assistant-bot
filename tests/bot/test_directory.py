from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest

from assistant.bot.directory import DirectoryCrawler
from assistant.core.services import groups
from assistant.core.services.group_names import GroupHeader
from tests.stubs import StubCalendars

NIGHT = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)  # 03:30 in Moscow
DAY = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)  # 12:00 in Moscow
HEADER = (
    "BEGIN:VCALENDAR\r\nX-WR-CALNAME:ИКБО-63-24\r\nBEGIN:X-SCHEDULE-VERSION\r\n"
    "X-SV-END:2026-12-30T21:00:00.0000000Z\r\nEND:X-SCHEDULE-VERSION\r\n"
).encode()


async def no_wait(seconds: float) -> None:
    return None


def crawler(sessionmaker, moment: datetime, calendars: StubCalendars | None = None):
    return DirectoryCrawler(
        sessionmaker, calendars or StubCalendars(), clock=lambda: moment, sleep=no_wait
    )


async def finished(sessionmaker, job: str, moment: datetime, groups_known: int = 0) -> None:
    async with sessionmaker() as session:
        await groups.record_run(session, job, moment, "test")
        for number in range(1, groups_known + 1):
            header = GroupHeader(f"ГРУППА-{number:03d}", date(2026, 12, 31))
            await groups.remember(session, number, header, moment)
        await session.commit()


async def test_the_first_crawl_runs_at_once_even_by_day(sessionmaker) -> None:
    assert await crawler(sessionmaker, DAY).due() == "full"


async def test_crawls_run_only_at_night(sessionmaker) -> None:
    await finished(sessionmaker, groups.FULL_JOB, DAY - timedelta(days=8), groups_known=120)
    assert await crawler(sessionmaker, DAY).due() is None
    assert await crawler(sessionmaker, NIGHT).due() == "full"


@pytest.mark.parametrize(
    ("full_ago", "quick_ago", "known", "expected"),
    [
        (timedelta(days=2), None, 120, "quick"),
        (timedelta(hours=20), None, 120, None),  # the full crawl was last night
        (timedelta(days=3), timedelta(hours=20), 120, None),  # so was the quick one
        (timedelta(days=3), timedelta(days=1), 120, "quick"),
        (timedelta(days=7), timedelta(hours=1), 120, "full"),
        (timedelta(days=1), None, 5, "full"),  # the last full crawl found too little: retry
    ],
)
async def test_which_crawl_is_due_at_night(
    sessionmaker, full_ago, quick_ago, known, expected
) -> None:
    await finished(sessionmaker, groups.FULL_JOB, NIGHT - full_ago, groups_known=known)
    if quick_ago is not None:
        await finished(sessionmaker, groups.QUICK_JOB, NIGHT - quick_ago)
    assert await crawler(sessionmaker, NIGHT).due() == expected


async def test_a_step_runs_the_due_crawl(sessionmaker, monkeypatch) -> None:
    monkeypatch.setattr(groups, "FIRST_UPPER", 3)
    monkeypatch.setattr(groups, "BEYOND_LAST", 0)
    calendars = StubCalendars()
    calendars.bodies[groups.calendar_url(2)] = HEADER
    assert await crawler(sessionmaker, DAY, calendars).step() == "full"
    async with sessionmaker() as session:
        assert [g.name for g in await groups.search(session, "ИКБО", date(2026, 10, 1))] == [
            "ИКБО-63-24"
        ]
        assert await groups.last_run(session, groups.FULL_JOB) == DAY
    assert await crawler(sessionmaker, DAY, calendars).step() is None


async def test_stop_ends_the_loop(sessionmaker) -> None:
    await finished(sessionmaker, groups.FULL_JOB, DAY, groups_known=120)
    worker = DirectoryCrawler(sessionmaker, StubCalendars(), clock=lambda: DAY, check_every=3600)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await asyncio.wait_for(task, 1)
    assert task.done() and not task.cancelled()
