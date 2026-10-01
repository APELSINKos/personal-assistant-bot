from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from assistant.core.models import JobRun, MireaGroup
from assistant.core.services import groups
from assistant.core.services.group_names import GroupHeader
from tests.stubs import StubCalendars

NOW = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)  # 04:00 in Moscow
TODAY = date(2026, 10, 1)
SEMESTER_END = date(2026, 12, 31)


def header(name: str, end: str | None = "2026-12-30T21:00:00.0000000Z") -> bytes:
    """The first lines of a MIREA group calendar, as the crawler reads them."""
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//github.com/ical-org/ical.net//NONSGML ical.net//EN",
        "VERSION:2.0",
        f"X-WR-CALNAME:{name}",
    ]
    if end is not None:
        lines += ["BEGIN:X-SCHEDULE-VERSION", f"X-SV-END:{end}", "END:X-SCHEDULE-VERSION"]
    return ("\r\n".join(lines) + "\r\n").encode()


async def add(session, group_id: int, name: str, end: date = SEMESTER_END) -> None:
    await groups.remember(session, group_id, GroupHeader(name, end), NOW)
    await session.commit()


async def test_search_by_any_spelling(session) -> None:
    for group_id, name in [(4805, "ИКБО-63-24"), (4804, "ИКБО-62-24"), (4900, "ИНБО-63-24")]:
        await add(session, group_id, name)
    await add(session, 100, "ИКБО-63-20", end=date(2021, 1, 31))  # an ended semester
    names = lambda found: [g.name for g in found]  # noqa: E731
    assert names(await groups.search(session, "ИКБО-63-24", TODAY)) == ["ИКБО-63-24"]
    assert names(await groups.search(session, "икбо 63", TODAY)) == ["ИКБО-63-24"]
    assert names(await groups.search(session, "ikbo-63-24", TODAY)) == ["ИКБО-63-24"]
    # «63-24» is inside two names; neither starts with it, so they come by name.
    assert names(await groups.search(session, "63-24", TODAY)) == ["ИКБО-63-24", "ИНБО-63-24"]
    # Names that start with the query come before names that only contain it.
    assert names(await groups.search(session, "ИКБО", TODAY)) == ["ИКБО-62-24", "ИКБО-63-24"]
    assert await groups.search(session, " — ", TODAY) == []
    assert await groups.search(session, "ЯЯЯ", TODAY) == []


async def test_search_shows_ten_at_most(session) -> None:
    for number in range(1, 16):
        await add(session, 1000 + number, f"ИКБО-{number:02d}-24")
    found = await groups.search(session, "ИКБО", TODAY)
    assert len(found) == 10 and found[0].name == "ИКБО-01-24"


async def test_remember_updates_a_known_group(session) -> None:
    await add(session, 4805, "ИКБО-63-24")
    later = NOW + timedelta(days=7)
    await groups.remember(session, 4805, GroupHeader("ИКБО-63-24", date(2027, 6, 30)), later)
    await session.commit()
    session.expire_all()
    group = await groups.get(session, 4805)
    assert group is not None and group.semester_end == date(2027, 6, 30) and group.seen_at == later
    assert await groups.count(session) == 1 and await groups.max_id(session) == 4805


class Pace:
    """A fake clock for the crawl's pacing: sleeping moves it forward."""

    def __init__(self) -> None:
        self.time = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.time

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.time += seconds


async def test_crawl_keeps_current_groups_and_follows_the_last_one(sessionmaker, session) -> None:
    calendars = StubCalendars()
    calendars.bodies[groups.calendar_url(2)] = header("ИКБО-63-24")
    calendars.bodies[groups.calendar_url(3)] = header("ИВБО-02-20", end=None)  # an old group
    calendars.bodies[groups.calendar_url(4)] = header("ХХБО-01-21", "2021-06-30T21:00:00Z")
    calendars.bodies[groups.calendar_url(5)] = b"<!DOCTYPE html><html>404</html>"
    calendars.bodies[groups.calendar_url(9)] = header("КМБО-14-25")  # past the first upper end
    pace = Pace()
    result = await groups.crawl(
        sessionmaker,
        calendars,
        1,
        6,
        now=lambda: NOW,
        sleep=pace.sleep,
        monotonic=pace.monotonic,
    )
    # Finding 9 moved the upper end to 9 + 300; the stub knows nothing past it.
    assert result == groups.CrawlResult(checked=309, found=2, highest=9)
    rows = (await session.scalars(select(MireaGroup).order_by(MireaGroup.id))).all()
    assert [(g.id, g.name, g.name_key, g.semester_end) for g in rows] == [
        (2, "ИКБО-63-24", "икбо6324", SEMESTER_END),
        (9, "КМБО-14-25", "кмбо1425", SEMESTER_END),
    ]
    # At most three requests a second: every request after the first waits for its turn.
    assert len(pace.sleeps) == 308 and set(pace.sleeps) == {0.333}


async def test_crawl_stops_when_asked(sessionmaker) -> None:
    calendars = StubCalendars()
    stop = asyncio.Event()
    stop.set()
    result = await groups.crawl(sessionmaker, calendars, 1, 100, stop=stop)
    assert result == groups.CrawlResult(0, 0, 0) and calendars.requests == []


async def test_a_full_crawl_prunes_what_it_no_longer_sees(sessionmaker, session, monkeypatch):
    monkeypatch.setattr(groups, "FIRST_UPPER", 3)
    monkeypatch.setattr(groups, "BEYOND_LAST", 0)
    monkeypatch.setattr(groups, "PRUNE_MIN_FOUND", 1)
    await add(session, 7, "УДАЛЁННАЯ-01-20")  # gone from MIREA since the last crawl
    calendars = StubCalendars()
    calendars.bodies[groups.calendar_url(1)] = header("ИКБО-63-24")
    pace = Pace()
    later = NOW + timedelta(days=7)
    result = await groups.full_crawl(
        sessionmaker, calendars, now=lambda: later, sleep=pace.sleep, monotonic=pace.monotonic
    )
    assert result.found == 1
    session.expire_all()
    assert [g.id for g in (await session.scalars(select(MireaGroup))).all()] == [1]
    run = await session.get(JobRun, groups.FULL_JOB)
    assert run is not None and run.finished_at == later
    assert run.info == "checked 7, found 1, removed 1"


async def test_a_failed_full_crawl_keeps_the_directory(sessionmaker, session, monkeypatch) -> None:
    monkeypatch.setattr(groups, "FIRST_UPPER", 5)
    monkeypatch.setattr(groups, "BEYOND_LAST", 0)
    for group_id in range(1, 4):
        await add(session, group_id, f"ИКБО-0{group_id}-24")
    pace = Pace()
    later = NOW + timedelta(days=7)
    # MIREA is down: every request fails, nothing is found.
    result = await groups.full_crawl(
        sessionmaker,
        StubCalendars(),
        now=lambda: later,
        sleep=pace.sleep,
        monotonic=pace.monotonic,
    )
    assert result.found == 0
    session.expire_all()
    assert await groups.count(session) == 3  # the directory survives the outage
    assert await groups.last_run(session, groups.FULL_JOB) == later


async def test_a_quick_crawl_reads_only_the_newest_numbers(sessionmaker, session, monkeypatch):
    monkeypatch.setattr(groups, "QUICK_BEHIND", 2)
    monkeypatch.setattr(groups, "BEYOND_LAST", 3)
    calendars = StubCalendars()
    assert await groups.quick_crawl(sessionmaker, calendars) == groups.CrawlResult(0, 0, 0)
    await add(session, 10, "ИКБО-10-24")
    calendars.bodies[groups.calendar_url(12)] = header("ИКБО-12-24")
    pace = Pace()
    result = await groups.quick_crawl(
        sessionmaker, calendars, now=lambda: NOW, sleep=pace.sleep, monotonic=pace.monotonic
    )
    assert calendars.requests[0] == groups.calendar_url(8)  # 10 − 2
    assert calendars.requests[-1] == groups.calendar_url(15)  # 12 + 3
    assert result == groups.CrawlResult(checked=8, found=1, highest=12)
    assert await groups.last_run(session, groups.QUICK_JOB) == NOW


async def test_the_directory_is_being_built_until_a_full_crawl_finishes(session) -> None:
    await add(session, 4805, "ИКБО-63-24")  # found by a crawl that is still running
    assert await groups.building(session) is True
    await groups.record_run(session, groups.QUICK_JOB, NOW, "checked 350, found 1")
    assert await groups.building(session) is True
    await groups.record_run(session, groups.FULL_JOB, NOW, "checked 6000, found 1")
    assert await groups.building(session) is False
