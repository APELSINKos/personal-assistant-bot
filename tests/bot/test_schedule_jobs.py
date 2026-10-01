from __future__ import annotations

import asyncio
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
    # Another user of the group keeps rows in the table, so the rebuilt lessons get new ids:
    # with the table emptied, SQLite would hand the freed ids out again in the same order.
    await connected(session, make_user, calendars, minutes=None, id=2)
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    await scheduler.send_lesson_alerts(moment)
    the_lesson = select(Lesson.id).where(Lesson.user_id == 1, Lesson.starts_at == LESSON)
    alerted = await session.scalar(the_lesson)
    assert alerted is not None
    # The six-hourly refresh rebuilds every lesson row right after the alert went out.
    async with sessionmaker() as other:
        user = await other.get(User, 1)
        assert user is not None
        await schedule.refresh(other, user, calendars, moment)
        await other.commit()
    rebuilt = await session.scalar(the_lesson)
    assert rebuilt is not None and rebuilt != alerted  # the same lesson, a new row
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


async def test_one_broken_source_does_not_hold_up_the_queue(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, monkeypatch, caplog
) -> None:
    await connected(session, make_user, calendars, id=1)
    await connected(session, make_user, calendars, id=2)
    original = schedule.refresh

    async def flaky(session, user, calendars, now=None):
        if user.id == 1:
            raise OSError("the parser did not start")
        return await original(session, user, calendars, now)

    monkeypatch.setattr(schedule, "refresh", flaky)
    due = CONNECTED + timedelta(hours=7)
    with caplog.at_level(logging.WARNING, logger="assistant.bot.scheduler"):
        assert await at(due, bot, sessionmaker, meteo, cbr, calendars).refresh_schedules(due) == 1
    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage() == (
        "schedule of user 1 not refreshed: OSError('the parser did not start')"
    )
    assert warning.exc_info is not None  # with the traceback
    session.expire_all()
    first, second = await schedule.get_source(session, 1), await schedule.get_source(session, 2)
    assert first is not None and first.next_refresh_at == schedule.next_refresh(1, due)
    assert second is not None and second.ok_at == due  # refreshed in the same pass


async def test_a_schedule_turned_off_meanwhile_is_skipped_quietly(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, monkeypatch, caplog
) -> None:
    await connected(session, make_user, calendars, id=1)
    await connected(session, make_user, calendars, id=2)
    listed = schedule.due_sources

    async def then_turned_off(session, now, limit):
        due = await listed(session, now, limit)
        async with sessionmaker() as other:  # the first user disconnects the schedule right then
            await schedule.disconnect(other, 1)
            await other.commit()
        return due

    monkeypatch.setattr(schedule, "due_sources", then_turned_off)
    due = CONNECTED + timedelta(hours=7)
    with caplog.at_level(logging.WARNING, logger="assistant.bot.scheduler"):
        assert await at(due, bot, sessionmaker, meteo, cbr, calendars).refresh_schedules(due) == 1
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    session.expire_all()
    source = await schedule.get_source(session, 2)
    assert source is not None and source.ok_at == due


async def test_without_a_downloader_nothing_is_refreshed(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user
) -> None:
    await connected(session, make_user, calendars)
    due = CONNECTED + timedelta(hours=7)
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: due)
    assert await scheduler.refresh_schedules(due) == 0


async def test_a_tick_does_not_wait_for_the_refresh(
    bot, sessionmaker, session, meteo, cbr, calendars, make_user, fake, monkeypatch
) -> None:
    await connected(session, make_user, calendars)
    moment = LESSON - timedelta(minutes=15)
    scheduler = at(moment, bot, sessionmaker, meteo, cbr, calendars)
    passes: list[datetime] = []
    release, over = asyncio.Event(), asyncio.Event()

    async def slow_refresh(now: datetime) -> int:
        passes.append(now)
        await release.wait()  # a slow download, or a parse queued behind users' uploads
        over.set()
        return 1

    monkeypatch.setattr(scheduler, "refresh_schedules", slow_refresh)
    await asyncio.wait_for(scheduler.tick(), 1)
    assert fake.sent_texts() == [ALERT]  # the lesson alert went out on time
    await asyncio.wait_for(scheduler.tick(), 1)
    assert passes == [moment]  # no second refresh beside the one in flight
    release.set()
    await asyncio.wait_for(over.wait(), 1)
    over.clear()
    await scheduler.tick()
    await asyncio.wait_for(over.wait(), 1)
    assert passes == [moment, moment]  # once it is over, the next tick starts the next one


async def test_a_failing_refresh_is_logged(
    bot, sessionmaker, meteo, cbr, calendars, monkeypatch, caplog
) -> None:
    scheduler = at(CONNECTED, bot, sessionmaker, meteo, cbr, calendars)
    failed = asyncio.Event()

    async def broken(now: datetime) -> int:
        failed.set()
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(scheduler, "refresh_schedules", broken)
    with caplog.at_level(logging.ERROR, logger="assistant.bot.scheduler"):
        await scheduler.tick()
        await asyncio.wait_for(failed.wait(), 1)
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == "scheduler job schedules failed"
    assert record.exc_info is not None


async def test_stop_lets_the_refresh_in_flight_finish(
    bot, sessionmaker, meteo, cbr, calendars, monkeypatch
) -> None:
    scheduler = Scheduler(
        bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: CONNECTED, calendars=calendars
    )
    started, release, finished = asyncio.Event(), asyncio.Event(), []

    async def slow_refresh(now: datetime) -> int:
        started.set()
        await release.wait()
        finished.append(now)  # its writes
        return 1

    monkeypatch.setattr(scheduler, "refresh_schedules", slow_refresh)
    task = asyncio.create_task(scheduler.run())
    await asyncio.wait_for(started.wait(), 1)
    scheduler.stop()
    await asyncio.sleep(0.05)
    assert not task.done()  # run() waits for the refresh instead of leaving it behind
    release.set()
    await asyncio.wait_for(task, 1)
    assert finished == [CONNECTED] and not task.cancelled()


async def test_a_cancelled_run_cancels_the_refresh_too(
    bot, sessionmaker, meteo, cbr, calendars, monkeypatch
) -> None:
    scheduler = Scheduler(
        bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: CONNECTED, calendars=calendars
    )
    stuck, refreshing, refresh_cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hanging_reminders(now: datetime) -> int:
        stuck.set()
        await asyncio.Event().wait()  # Telegram does not answer
        return 0

    async def hanging_refresh(now: datetime) -> int:
        refreshing.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            refresh_cancelled.set()
            raise
        return 0

    monkeypatch.setattr(scheduler, "deliver_reminders", hanging_reminders)
    monkeypatch.setattr(scheduler, "refresh_schedules", hanging_refresh)
    task = asyncio.create_task(scheduler.run())
    await asyncio.wait_for(asyncio.gather(stuck.wait(), refreshing.wait()), 1)
    task.cancel()  # the bot's shutdown grace ran out in the middle of a tick
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(refresh_cancelled.wait(), 1)  # nothing is left running


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
