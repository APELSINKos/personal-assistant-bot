from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import func, select

from assistant.bot.scheduler import Scheduler
from assistant.core.models import Lesson, LessonAlert, User
from assistant.core.services import groups, schedule
from assistant.core.services.group_names import GroupHeader
from tests.stubs import StubCalendars

MIREA = (
    Path(__file__).resolve().parents[1] / "fixtures" / "schedule" / "mirea_ikbo_63_24.ics"
).read_bytes()
CONNECTED = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
LESSON = datetime(2026, 9, 30, 9, 40, tzinfo=UTC)  # ПР Разработка баз данных, 12:40 in Moscow
ALERT = "🎓 Через 15 мин: ПР Разработка баз данных · И-212-б (В-78)"


@pytest.fixture
def calendars() -> StubCalendars:
    stub = StubCalendars()
    stub.bodies[groups.calendar_url(4805)] = MIREA
    return stub


def at(moment: datetime, bot, sessionmaker, meteo, cbr, calendars) -> Scheduler:
    return Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: moment, calendars=calendars)


async def connected(session, make_user, calendars, minutes: int | None = 15, **user) -> User:
    person = await make_user(morning_enabled=False, **user)
    await groups.remember(session, 4805, GroupHeader("ИКБО-63-24", date(2026, 12, 31)), CONNECTED)
    await schedule.connect_mirea(session, person, 4805, calendars, CONNECTED)
    await schedule.set_alert_minutes(session, person.id, minutes)
    await session.commit()
    return person


async def alerts(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(LessonAlert)) or 0)


async def test_an_alert_before_a_lesson(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars)
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    assert await scheduler.send_lesson_alerts(moment) == 1
    assert fake.sent_texts() == [ALERT]
    assert fake.of(SendMessage)[0].reply_markup is None  # no snooze buttons for lessons
    assert await scheduler.send_lesson_alerts(moment + timedelta(minutes=1)) == 0
    assert await alerts(session) == 1


async def test_a_late_alert_says_how_long_is_left(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars)
    moment = LESSON - timedelta(minutes=7, seconds=30)  # the bot was down for a while
    await at(moment, bot, sessionmaker, meteo, cbr, calendars).send_lesson_alerts(moment)
    assert fake.sent_texts() == [ALERT.replace("15 мин", "8 мин")]


async def test_an_alert_is_not_sent_again_after_a_refresh(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars)
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    await scheduler.send_lesson_alerts(moment)
    # The six-hourly refresh rebuilds every lesson row right after the alert went out.
    async with sessionmaker() as other:
        user = await other.get(User, 1)
        assert user is not None
        await schedule.refresh(other, user, calendars, moment)
        await other.commit()
    assert await scheduler.send_lesson_alerts(moment + timedelta(minutes=2)) == 0
    assert fake.sent_texts() == [ALERT]


async def test_no_alerts_when_they_are_off(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars, minutes=None)
    moment = LESSON - timedelta(minutes=15)
    assert (
        await at(moment, bot, sessionmaker, meteo, cbr, calendars).send_lesson_alerts(moment) == 0
    )
    assert fake.calls == []


async def test_a_blocked_user_is_marked_and_skipped(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars)
    fake.errors.append(
        TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="blocked")
    )
    moment = LESSON - timedelta(minutes=15)
    assert (
        await at(moment, bot, sessionmaker, meteo, cbr, calendars).send_lesson_alerts(moment) == 0
    )
    user = await session.get(User, 1)
    await session.refresh(user)
    assert user is not None and user.bot_blocked
    assert await alerts(session) == 0


async def test_a_network_failure_retries_on_the_next_tick(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake
) -> None:
    await connected(session, make_user, calendars)
    fake.errors.append(
        TelegramNetworkError(method=SendMessage(chat_id=1, text="x"), message="timeout")
    )
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    assert await scheduler.send_lesson_alerts(moment) == 0
    assert await scheduler.send_lesson_alerts(moment + timedelta(seconds=20)) == 1


async def test_sources_are_refreshed_when_due(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user
) -> None:
    await connected(session, make_user, calendars)
    calendars.requests.clear()
    early = CONNECTED + timedelta(hours=1)
    assert await at(early, bot, sessionmaker, meteo, cbr, calendars).refresh_schedules(early) == 0
    due = CONNECTED + timedelta(hours=7)
    assert await at(due, bot, sessionmaker, meteo, cbr, calendars).refresh_schedules(due) == 1
    assert calendars.requests == [groups.calendar_url(4805)]
    session.expire_all()
    source = await schedule.get_source(session, 1)
    assert source is not None and source.ok_at == due


async def test_a_failed_refresh_is_only_logged(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, caplog
) -> None:
    await connected(session, make_user, calendars)
    calendars.errors[groups.calendar_url(4805)] = "unreachable"
    due = CONNECTED + timedelta(hours=7)
    with caplog.at_level(logging.WARNING, logger="assistant.bot.scheduler"):
        assert await at(due, bot, sessionmaker, meteo, cbr, calendars).refresh_schedules(due) == 1
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [
        "schedule of user 1 not refreshed: unreachable"
    ]
    count = await session.scalar(select(func.count()).select_from(Lesson))
    assert count == 39  # the timetable is still there


async def test_without_a_downloader_nothing_is_refreshed(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user
) -> None:
    await connected(session, make_user, calendars)
    due = CONNECTED + timedelta(hours=7)
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: due)
    assert await scheduler.refresh_schedules(due) == 0


async def test_cleanup_forgets_old_alerts(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user
) -> None:
    await connected(session, make_user, calendars)
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    await scheduler.send_lesson_alerts(moment)
    assert await scheduler.cleanup(LESSON + timedelta(days=1)) == 0
    assert await scheduler.cleanup(LESSON + timedelta(days=2, seconds=1)) == 1
    assert await alerts(session) == 0
