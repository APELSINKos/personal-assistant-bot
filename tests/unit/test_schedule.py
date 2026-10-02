from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import Lesson, ScheduleKind, ScheduleSource, User, WeekLabel
from assistant.core.services import groups, ical, schedule
from assistant.core.services.group_names import GroupHeader
from tests.stubs import StubCalendars

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
MIREA = (FIXTURES / "mirea_ikbo_63_24.ics").read_bytes()
FOREIGN = (FIXTURES / "foreign.ics").read_bytes()
OUTLOOK = (FIXTURES / "outlook.ics").read_bytes()
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # Monday, 15:00 in Moscow
GROUP_URL = groups.calendar_url(4805)


def utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


@pytest.fixture
def calendars() -> StubCalendars:
    stub = StubCalendars()
    stub.bodies[GROUP_URL] = MIREA
    stub.bodies["https://uni.example/t.ics"] = FOREIGN
    return stub


async def with_group(session) -> None:
    await groups.remember(session, 4805, GroupHeader("ИКБО-63-24", date(2026, 12, 31)), NOW)
    await session.commit()


async def lesson_count(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(Lesson)) or 0)


def meanwhile(calendars, url: str, action, monkeypatch) -> None:
    """`action` runs once, while `url` is being downloaded, as the other process (bot or API)
    may."""
    fetch = calendars.fetch
    pending = [action]

    async def fetch_after(link: str) -> bytes:
        if link == url and pending:
            await pending.pop()()
        return await fetch(link)

    monkeypatch.setattr(calendars, "fetch", fetch_after)


async def test_connect_a_mirea_group(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    source = await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    assert source.kind is ScheduleKind.MIREA and source.mirea_id == 4805
    assert source.url == GROUP_URL and source.title == "ИКБО-63-24"
    assert source.ok_at == source.fetched_at == NOW and source.error is None
    assert source.next_refresh_at == NOW + timedelta(hours=6, minutes=1)  # user 1 % 60
    # Six biweekly series from 21 September (now − 7 days) to the semester's end.
    assert await lesson_count(session) == 39
    assert await schedule.lessons_ahead(session, user.id, NOW) == 36
    (lesson,) = await schedule.lessons_on(session, user, date(2026, 9, 30))
    assert (lesson.starts_at, lesson.kind, lesson.title, lesson.room) == (
        utc(2026, 9, 30, 9, 40),
        "ПР",
        "Разработка баз данных",
        "И-212-б (В-78)",
    )
    assert await schedule.week_label(session, user.id, date(2026, 9, 30)) == "5 неделя"
    assert await schedule.week_label(session, user.id, date(2026, 10, 5)) == "6 неделя"
    assert await schedule.week_label(session, user.id, date(2027, 1, 20)) is None


async def test_connecting_an_unknown_group(session, make_user, calendars) -> None:
    user = await make_user()
    with pytest.raises(NotFound):
        await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    assert calendars.requests == []


async def test_connect_a_link(session, make_user, calendars) -> None:
    user = await make_user()
    source = await schedule.connect_url(
        session, user, " webcal://uni.example/t.ics ", calendars, NOW
    )
    await session.commit()
    assert source.kind is ScheduleKind.URL and source.url == "https://uni.example/t.ics"
    assert source.title == "Physics 101" and source.body is None
    assert calendars.requests == ["https://uni.example/t.ics"]
    assert await lesson_count(session) > 0


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://uni.example/t.ics", "forbidden_host"),  # refused before any request
        ("https://uni.example/gone.ics", "unreachable"),
    ],
)
async def test_a_refused_link_stores_nothing(session, make_user, calendars, url, reason) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput) as caught:
        await schedule.connect_url(session, user, url, calendars, NOW)
    assert caught.value.params == {"field": "url", "reason": reason}
    assert await schedule.get_source(session, user.id) is None


async def test_connect_a_file(session, make_user) -> None:
    user = await make_user()
    source = await schedule.connect_file(session, user, OUTLOOK, "Английский.ics", NOW)
    await session.commit()
    assert source.kind is ScheduleKind.FILE and source.title == "Английский"
    assert source.body == OUTLOOK and source.url is None
    assert [
        lesson.title for lesson in await schedule.lessons_on(session, user, date(2026, 9, 29))
    ] == ["Английский язык"]


async def test_a_file_that_is_not_a_calendar_or_too_big(session, make_user) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput) as caught:
        await schedule.connect_file(session, user, b"%PDF-1.7", "timetable.pdf", NOW)
    assert caught.value.params == {"field": "calendar", "reason": "not_calendar"}
    with pytest.raises(InvalidInput) as caught:
        await schedule.connect_file(session, user, b"B" * (schedule.FILE_LIMIT + 1), "x.ics", NOW)
    assert caught.value.params == {"field": "file", "reason": "too_large"}
    assert await schedule.get_source(session, user.id) is None


async def test_a_failed_switch_keeps_the_old_source(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    for attempt in (
        schedule.connect_url(session, user, "https://uni.example/gone.ics", calendars, NOW),
        schedule.connect_file(session, user, b"not a calendar", "x.ics", NOW),
    ):
        with pytest.raises(InvalidInput):
            await attempt
    await session.commit()
    user_id = user.id  # read before expire_all(): a lazy load would need a greenlet
    session.expire_all()
    source = await schedule.get_source(session, user_id)
    assert source is not None and source.kind is ScheduleKind.MIREA and source.mirea_id == 4805
    assert await lesson_count(session) == 39


async def test_a_failed_refresh_keeps_the_lessons(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    calendars.errors[GROUP_URL] = "unreachable"  # MIREA is down
    later = NOW + timedelta(hours=6)
    source = await schedule.refresh(session, user, calendars, later)
    await session.commit()
    assert source.error == "unreachable" and source.fetched_at == later and source.ok_at == NOW
    assert source.next_refresh_at == later + timedelta(hours=6, minutes=1)
    assert await lesson_count(session) == 39
    assert not schedule.is_stale(source, NOW + timedelta(days=3))
    assert schedule.is_stale(source, NOW + timedelta(days=3, minutes=1))
    del calendars.errors[GROUP_URL]  # back again
    source = await schedule.refresh(session, user, calendars, later + timedelta(hours=6))
    assert source.error is None and source.ok_at == later + timedelta(hours=6)


@pytest.mark.parametrize("fails", [False, True], ids=["downloaded", "download-failed"])
async def test_a_refresh_writes_nothing_once_the_source_was_switched(
    session, sessionmaker, make_user, calendars, monkeypatch, fails
) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()

    async def switch() -> None:
        # At the very moment the group was connected: only what the source is tells them apart.
        async with sessionmaker() as other:
            owner = await other.get_one(User, user.id)
            await schedule.connect_url(other, owner, "https://uni.example/t.ics", calendars, NOW)
            await other.commit()

    meanwhile(calendars, GROUP_URL, switch, monkeypatch)
    if fails:
        calendars.errors[GROUP_URL] = "unreachable"
    source = await schedule.refresh(session, user, calendars, NOW + timedelta(hours=6))
    await session.commit()
    # The link as it was connected: neither the group's lessons nor its error or times.
    assert (source.kind, source.title, source.error) == (ScheduleKind.URL, "Physics 101", None)
    assert source.fetched_at == source.ok_at == NOW
    lessons = await schedule.lessons_between(
        session, user.id, NOW - timedelta(days=7), NOW + timedelta(days=120)
    )
    titles = {lesson.title for lesson in lessons}
    assert "Physics lecture" in titles and "Разработка баз данных" not in titles


async def test_a_refresh_writes_nothing_once_another_refresh_came_first(
    session, sessionmaker, make_user, calendars, monkeypatch
) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    first = NOW + timedelta(hours=6)

    async def refresh_elsewhere() -> None:
        async with sessionmaker() as other:
            owner = await other.get_one(User, user.id)
            await schedule.refresh(other, owner, calendars, first)
            await other.commit()

    meanwhile(calendars, GROUP_URL, refresh_elsewhere, monkeypatch)
    source = await schedule.refresh(session, user, calendars, first + timedelta(minutes=1))
    await session.commit()
    # The same group both times: only fetched_at tells that the source changed meanwhile.
    assert source.fetched_at == source.ok_at == first
    assert source.next_refresh_at == first + timedelta(hours=6, minutes=1)


@pytest.mark.parametrize("fails", [False, True], ids=["downloaded", "download-failed"])
async def test_a_refresh_of_a_source_disconnected_meanwhile_is_not_found(
    session, sessionmaker, make_user, calendars, monkeypatch, fails
) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()

    async def disconnect() -> None:
        async with sessionmaker() as other:
            assert await schedule.disconnect(other, user.id)
            await other.commit()

    meanwhile(calendars, GROUP_URL, disconnect, monkeypatch)
    if fails:
        calendars.errors[GROUP_URL] = "unreachable"
    with pytest.raises(NotFound):
        await schedule.refresh(session, user, calendars, NOW + timedelta(hours=6))
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(ScheduleSource)) == 0
    assert await lesson_count(session) == 0


async def test_a_file_is_read_again_as_the_window_moves(session, make_user) -> None:
    user = await make_user()
    await schedule.connect_file(session, user, MIREA, "group.ics", NOW)
    await session.commit()
    month_later = NOW + timedelta(days=30)
    await schedule.refresh(session, user, StubCalendars(), month_later)  # no download at all
    await session.commit()
    first = await session.scalar(select(func.min(Lesson.starts_at)))
    assert first is not None and first >= month_later - schedule.WINDOW_BEFORE


async def test_disconnect(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    assert await schedule.disconnect(session, user.id)
    await session.commit()
    assert await schedule.get_source(session, user.id) is None
    assert await lesson_count(session) == 0
    assert (await session.scalars(select(WeekLabel))).all() == []
    assert not await schedule.disconnect(session, user.id)
    with pytest.raises(NotFound):
        await schedule.refresh(session, user, calendars, NOW)


async def test_alert_minutes(session, make_user) -> None:
    user = await make_user()
    with pytest.raises(NotFound):
        await schedule.set_alert_minutes(session, user.id, 15)
    await schedule.connect_file(session, user, OUTLOOK, "x.ics", NOW)
    source = await schedule.set_alert_minutes(session, user.id, 15)
    assert source.lesson_reminder_minutes == 15
    with pytest.raises(InvalidInput):
        await schedule.set_alert_minutes(session, user.id, 7)
    assert (
        await schedule.set_alert_minutes(session, user.id, None)
    ).lesson_reminder_minutes is None


async def test_refresh_by_hand_waits_a_minute(session, make_user) -> None:
    user = await make_user()
    source = await schedule.connect_file(session, user, OUTLOOK, "x.ics", NOW)
    assert schedule.refresh_wait(source, NOW + timedelta(seconds=20)) == 40.0
    assert schedule.refresh_wait(source, NOW + timedelta(minutes=1)) == 0.0


def test_three_downloads_or_parses_a_minute_per_user() -> None:
    now = [100.0]
    budget = schedule.attempt_limiter(lambda: now[0])
    assert [budget.check(1) for _ in range(3)] == [None, None, None]
    assert budget.check(1) == 60.0  # a refused attempt does not count
    assert budget.check(2) is None  # every user has a budget of their own
    now[0] = 160.0
    assert budget.check(1) is None


async def test_due_sources_the_longest_waiting_first(session, make_user) -> None:
    for user_id in (1, 2, 3):
        user = await make_user(id=user_id)
        await schedule.connect_file(
            session, user, OUTLOOK, "x.ics", NOW + timedelta(minutes=user_id)
        )
    await session.commit()
    due = NOW + timedelta(hours=7)
    assert await schedule.due_sources(session, due, 2) == [1, 2]
    assert await schedule.due_sources(session, NOW + timedelta(hours=1), 5) == []


async def test_due_alerts(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await session.commit()
    start = utc(2026, 9, 30, 9, 40)  # ПР Разработка баз данных
    at = lambda minutes: start - timedelta(minutes=minutes)  # noqa: E731
    assert await schedule.due_alerts(session, at(15)) == []  # alerts are off by default
    await schedule.set_alert_minutes(session, user.id, 15)
    await session.commit()
    assert await schedule.due_alerts(session, at(16)) == []  # not yet
    ((lesson, owner, minutes),) = await schedule.due_alerts(session, at(15))
    assert (lesson.starts_at, owner.id, minutes) == (start, user.id, 15)
    assert len(await schedule.due_alerts(session, at(5))) == 1  # 10 minutes late: still sent
    assert await schedule.due_alerts(session, at(4)) == []  # more than 10 minutes late: dropped
    await schedule.mark_alerted(session, lesson, at(15))
    await schedule.mark_alerted(session, lesson, at(15))  # twice is harmless
    await session.commit()
    assert await schedule.due_alerts(session, at(10)) == []


async def test_an_alert_is_not_due_again_after_a_refresh(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await schedule.set_alert_minutes(session, user.id, 15)
    await session.commit()
    moment = utc(2026, 9, 30, 9, 25)
    ((lesson, _, _),) = await schedule.due_alerts(session, moment)
    await schedule.mark_alerted(session, lesson, moment)
    await schedule.refresh(session, user, calendars, moment)  # lessons rebuilt, new row ids
    await session.commit()
    assert await schedule.due_alerts(session, moment + timedelta(minutes=1)) == []


async def test_blocked_users_get_no_alerts(session, make_user, calendars) -> None:
    user = await make_user(bot_blocked=True)
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    await schedule.set_alert_minutes(session, user.id, 15)
    await session.commit()
    assert await schedule.due_alerts(session, utc(2026, 9, 30, 9, 25)) == []


async def test_forget_old_alerts(session, make_user, calendars) -> None:
    user = await make_user()
    await with_group(session)
    await schedule.connect_mirea(session, user, 4805, calendars, NOW)
    for lesson in await schedule.lessons_on(session, user, date(2026, 9, 30)):
        await schedule.mark_alerted(session, lesson, NOW)
    assert await schedule.forget_alerts(session, utc(2026, 10, 2)) == 1


async def test_a_day_is_the_users_own_day(session, make_user) -> None:
    # 23:30 in Moscow on 30 September is 06:30 on 1 October in Vladivostok.
    late = (
        b"BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:late\n"
        b"DTSTART;TZID=Europe/Moscow:20260930T233000\nDTEND;TZID=Europe/Moscow:20260930T235900\n"
        b"SUMMARY:Night class\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    user = await make_user(tz="Asia/Vladivostok")
    await schedule.connect_file(session, user, late, "late.ics", NOW)
    assert await schedule.lessons_on(session, user, date(2026, 9, 30)) == []
    (lesson,) = await schedule.lessons_on(session, user, date(2026, 10, 1))
    assert lesson.starts_at == utc(2026, 9, 30, 20, 30)


async def test_calendars_are_parsed_one_at_a_time(make_user, monkeypatch) -> None:
    running = most = 0
    lock = threading.Lock()

    def slow_parse(body: bytes, start: datetime, end: datetime, tz: str) -> ical.Timetable:
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return ical.Timetable(None, [], [])

    monkeypatch.setattr(ical, "parse_isolated", slow_parse)
    user = await make_user()
    await asyncio.gather(*(schedule._timetable(b"", user, NOW) for _ in range(4)))
    assert most == 1


async def test_precheck_refuses_a_bad_link_and_an_unknown_group(session) -> None:
    with pytest.raises(InvalidInput):
        await schedule.precheck(session, url="not a link")
    with pytest.raises(NotFound):
        await schedule.precheck(session, mirea_id=99_999)
    await schedule.precheck(session, url="webcal://uni.example/a.ics")  # a link it would try
