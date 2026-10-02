from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.exceptions import (
    ClientDecodeError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage
from sqlalchemy import select

from assistant.bot import scheduler as scheduler_module
from assistant.bot.keyboards import FireCb
from assistant.bot.scheduler import Scheduler
from assistant.core.models import FsmState, Habit, Reminder, ReminderStatus, Repeat, ShareCard
from assistant.core.services import reminders
from assistant.core.services.recurrence import Rule

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow
METHOD = SendMessage(chat_id=1, text="x")


@pytest.fixture
def scheduler(bot, sessionmaker, meteo, cbr) -> Scheduler:
    return Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: NOW)


async def add_reminder(
    session, user_id: int = 1, *, ago: timedelta = timedelta(minutes=1), text: str = "полить цветы"
) -> Reminder:
    due = NOW - ago
    reminder = Reminder(user_id=user_id, text=text, due_at=due, next_attempt_at=due)
    session.add(reminder)
    await session.commit()
    return reminder


async def reload(session, obj):
    await session.refresh(obj)
    return obj


async def test_delivers_due_reminder(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    await add_reminder(session, ago=-timedelta(minutes=5), text="future")
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы"]
    reminder = await reload(session, reminder)
    assert reminder.status == ReminderStatus.SENT and reminder.sent_at == NOW


@pytest.mark.parametrize(
    ("ago", "suffix"),
    [
        (timedelta(minutes=5), ""),
        (timedelta(minutes=30), " (было на 14:30)"),
        (timedelta(hours=20), " (было на 27 сент., 19:00)"),
    ],
)
async def test_late_mark(scheduler, session, make_user, fake, ago, suffix) -> None:
    await make_user(morning_enabled=False)
    await add_reminder(session, ago=ago)
    await scheduler.deliver_reminders(NOW)
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы" + suffix]


async def test_retry_after_does_not_count_and_stops_the_batch(
    scheduler, session, make_user, fake
) -> None:
    await make_user(morning_enabled=False)
    first = await add_reminder(session, ago=timedelta(minutes=2))
    second = await add_reminder(session, ago=timedelta(minutes=1))
    fake.errors.append(
        TelegramRetryAfter(method=METHOD, message="Too Many Requests", retry_after=7)
    )
    assert await scheduler.deliver_reminders(NOW) == 0
    assert len(fake.calls) == 1
    first, second = await reload(session, first), await reload(session, second)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 0)
    assert first.next_attempt_at == NOW + timedelta(seconds=7)
    assert second.status == ReminderStatus.PENDING


async def test_network_errors_back_off_then_fail(
    scheduler, session, make_user, fake, caplog
) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    moment = NOW
    delays = []
    for attempt in range(1, reminders.MAX_FAILURES + 1):
        error = (
            TelegramNetworkError(method=METHOD, message="timeout")
            if attempt % 2
            else TelegramServerError(method=METHOD, message="Bad Gateway")
        )
        fake.errors.append(error)
        await scheduler.deliver_reminders(moment)
        reminder = await reload(session, reminder)
        if attempt < reminders.MAX_FAILURES:
            assert (reminder.status, reminder.attempts) == (ReminderStatus.PENDING, attempt)
            delays.append((reminder.next_attempt_at - moment).total_seconds())
            moment = reminder.next_attempt_at
    assert delays == [30, 60, 300, 900, 3600, 10800]
    assert (reminder.status, reminder.attempts) == (ReminderStatus.FAILED, 7)
    gave_up = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert gave_up == [f"reminder {reminder.id} gave up after 7 attempts: network: timeout"]


async def test_blocked_user(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    first = await add_reminder(session, ago=timedelta(minutes=2))
    second = await add_reminder(session, ago=timedelta(minutes=1))
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user")
    )
    await scheduler.deliver_reminders(NOW)
    assert len(fake.calls) == 1
    assert (await reload(session, first)).status == ReminderStatus.FAILED
    assert (await reload(session, second)).status == ReminderStatus.PENDING
    assert (await reload(session, user)).bot_blocked
    assert await scheduler.deliver_reminders(NOW + timedelta(minutes=1)) == 0
    assert len(fake.calls) == 1


async def test_bad_request_fails_without_blocking(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    await scheduler.deliver_reminders(NOW)
    assert (await reload(session, reminder)).status == ReminderStatus.FAILED
    assert not (await reload(session, user)).bot_blocked


@pytest.mark.parametrize(
    "error",
    [
        ClientDecodeError("failed to decode", ValueError("bad json"), b"<html>"),
        TelegramNetworkError(method=METHOD, message="timeout"),
        TelegramServerError(method=METHOD, message="Bad Gateway"),
    ],
)
async def test_network_failure_stops_the_batch(scheduler, session, make_user, fake, error) -> None:
    await make_user(id=1, morning_enabled=False)
    await make_user(id=2, morning_enabled=False)
    first = await add_reminder(session, user_id=1, ago=timedelta(minutes=2), text="полить цветы")
    second = await add_reminder(session, user_id=2, ago=timedelta(minutes=1), text="call mom")
    fake.errors.append(error)
    assert await scheduler.deliver_reminders(NOW) == 0
    # Only the first one was attempted; a dropping network must not stall the tick with a
    # timeout per reminder. The second stays due, untouched, for the next tick.
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы"]
    first = await reload(session, first)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 1)
    assert first.next_attempt_at == NOW + timedelta(seconds=reminders.BACKOFF[0])
    second = await reload(session, second)
    assert (second.status, second.attempts) == (ReminderStatus.PENDING, 0)
    assert await scheduler.deliver_reminders(NOW + timedelta(seconds=1)) == 1
    assert (await reload(session, second)).status == ReminderStatus.SENT


async def test_unexpected_error_for_one_reminder_does_not_stop_the_batch(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(id=1, morning_enabled=False)
    await make_user(id=2, morning_enabled=False)
    first = await add_reminder(session, user_id=1, ago=timedelta(minutes=2), text="broken")
    await add_reminder(session, user_id=2, ago=timedelta(minutes=1), text="ok")
    original = scheduler_module.reminder_text

    def flaky(reminder, user, shown, now, t):
        if reminder.text == "broken":
            raise RuntimeError("boom")
        return original(reminder, user, shown, now, t)

    monkeypatch.setattr(scheduler_module, "reminder_text", flaky)
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: ok"]
    first = await reload(session, first)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 1)
    assert first.next_attempt_at == NOW + timedelta(seconds=reminders.BACKOFF[0])


# 23:30 Moscow = 20:30 UTC; the window lasts until 00:30 of the next local day.
AT_2345 = datetime(2026, 9, 28, 20, 45, tzinfo=UTC)
AT_0015 = datetime(2026, 9, 28, 21, 15, tzinfo=UTC)


async def test_digest_window_crossing_midnight_sends_once(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    assert await scheduler.send_digests(AT_2345) == 1
    assert fake.sent_texts()[0].startswith("☀️ Доброе утро, Test!")
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)
    assert await scheduler.send_digests(AT_0015) == 0
    assert len(fake.calls) == 1


async def test_digest_retries_after_network_error_inside_the_window(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(TelegramNetworkError(method=METHOD, message="timeout"))
    assert await scheduler.send_digests(AT_2345) == 0
    assert (await reload(session, user)).last_morning_date is None
    assert await scheduler.send_digests(AT_0015) == 1
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)


async def test_digest_skips_disabled_blocked_and_out_of_window(
    scheduler, session, make_user, fake
) -> None:
    await make_user(id=1, morning_time="23:30", morning_enabled=False)
    await make_user(id=2, morning_time="23:30", bot_blocked=True)
    await make_user(id=3, morning_time="08:00")
    assert await scheduler.send_digests(AT_2345) == 0
    assert fake.calls == []


async def test_digest_403_blocks_user(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: user is deactivated")
    )
    await scheduler.send_digests(AT_2345)
    user = await reload(session, user)
    assert user.bot_blocked and user.last_morning_date is None


async def test_digest_bad_request_sets_last_morning_date_without_retry(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    assert await scheduler.send_digests(AT_2345) == 0
    user = await reload(session, user)
    assert user.last_morning_date == date(2026, 9, 28)
    assert not user.bot_blocked
    assert await scheduler.send_digests(AT_0015) == 0
    assert len(fake.calls) == 1


async def test_digest_one_user_raising_does_not_stop_others(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(id=1, morning_time="23:30")
    await make_user(id=2, morning_time="23:30")
    original = Scheduler._digest

    async def flaky(self, user_id, day, now):
        if user_id == 1:
            raise RuntimeError("boom")
        return await original(self, user_id, day, now)

    monkeypatch.setattr(Scheduler, "_digest", flaky)
    assert await scheduler.send_digests(AT_2345) == 1
    assert len(fake.calls) == 1


async def test_tick_survives_a_failing_job(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(morning_time="15:00")

    async def broken(*args, **kwargs):
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(reminders, "due", broken)
    await scheduler.tick()
    assert fake.sent_texts()[0].startswith("☀️ Доброе утро")


async def test_cleanup_removes_only_old_dialogs(scheduler, session) -> None:
    session.add_all(
        [
            FsmState(
                chat_id=1,
                user_id=1,
                state="NoteForm:text",
                data={},
                updated_at=NOW - timedelta(hours=25),
            ),
            FsmState(
                chat_id=2,
                user_id=2,
                state="NoteForm:text",
                data={},
                updated_at=NOW - timedelta(hours=1),
            ),
        ]
    )
    await session.commit()
    assert await scheduler.cleanup(NOW) == 1
    assert [row.chat_id for row in (await session.scalars(select(FsmState))).all()] == [2]


async def test_cleanup_drops_expired_share_cards(scheduler, session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 9, 28))
    session.add(habit)
    await session.flush()
    session.add_all(
        [
            ShareCard(
                token="a" * 43,
                user_id=user.id,
                habit_id=habit.id,
                image=b"old",
                expires_at=NOW - timedelta(seconds=1),
            ),
            ShareCard(
                token="b" * 43,
                user_id=user.id,
                habit_id=habit.id,
                image=b"new",
                expires_at=NOW + timedelta(hours=1),
            ),
        ]
    )
    await session.commit()
    assert await scheduler.cleanup(NOW) == 1
    assert [card.token for card in (await session.scalars(select(ShareCard))).all()] == ["b" * 43]


async def test_english_reminder(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False, language="en")
    await add_reminder(session, ago=timedelta(minutes=30), text="call mom")
    await scheduler.deliver_reminders(NOW)
    assert fake.sent_texts() == ["⏰ Reminder: call mom (was due at 14:30)"]


async def test_digest_user_with_a_broken_zone_does_not_stop_others(
    scheduler, session, make_user, fake
) -> None:
    await make_user(id=1, morning_time="23:30", tz="Mars/Olympus")
    await make_user(id=2, morning_time="23:30")
    assert await scheduler.send_digests(AT_2345) == 1
    assert [call.chat_id for call in fake.of(SendMessage)] == [2]


async def test_stop_ends_run_without_waiting_for_the_interval(
    bot, sessionmaker, meteo, cbr, make_user
) -> None:
    await make_user(morning_enabled=False)
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: NOW)
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.05)  # the first tick runs, then the scheduler sleeps
    scheduler.stop()
    await asyncio.wait_for(task, 1)  # returns by itself: nothing was cancelled
    assert task.done() and not task.cancelled()


async def test_stop_lets_the_current_tick_finish(
    bot, sessionmaker, meteo, cbr, monkeypatch
) -> None:
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: NOW)
    started, finished = asyncio.Event(), []

    async def slow_tick() -> None:
        started.set()
        await asyncio.sleep(0.05)
        finished.append(True)

    monkeypatch.setattr(scheduler, "tick", slow_tick)
    task = asyncio.create_task(scheduler.run())
    await started.wait()
    scheduler.stop()  # in the middle of a tick
    await asyncio.wait_for(task, 1)
    assert finished == [True]


async def add_daily(session, *, time_local: str, occurrence: datetime, text: str = "таблетки"):
    reminder = Reminder(
        user_id=1,
        text=text,
        due_at=occurrence,
        next_attempt_at=occurrence,
        occurrence_at=occurrence,
        repeat=Repeat.DAILY,
        time_local=time_local,
        anchor_date=date(2026, 9, 1),
    )
    session.add(reminder)
    await session.commit()
    return reminder


async def test_fired_message_has_buttons(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    await scheduler.deliver_reminders(NOW)
    markup = fake.of(SendMessage)[-1].reply_markup
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [b.text for b in buttons] == ["+10 мин", "+1 ч", "Завтра", "✓ Готово"]
    first = FireCb.unpack(buttons[0].callback_data)
    assert (first.action, first.id) == ("10m", reminder.id)
    assert first.at == int(reminder.due_at.timestamp() // 60)


async def test_repeat_moves_to_the_next_firing(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: таблетки"]
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING and series.sent_at == NOW
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_catches_up_with_one_message(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    three_days_ago = datetime(2026, 9, 25, 6, 0, tzinfo=UTC)  # 09:00 Moscow
    series = await add_daily(session, time_local="09:00", occurrence=three_days_ago)
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: таблетки (было на 09:00)"]
    series = await reload(session, series)
    assert series.due_at == datetime(2026, 9, 29, 6, 0, tzinfo=UTC)
    assert await scheduler.deliver_reminders(NOW + timedelta(minutes=1)) == 0


async def test_blocked_user_keeps_the_series(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user")
    )
    await scheduler.deliver_reminders(NOW)
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)
    assert (await reload(session, user)).bot_blocked


async def test_bad_request_moves_a_series_on(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    await scheduler.deliver_reminders(NOW)
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING
    assert series.last_error == "Bad Request: chat not found"
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_survives_max_temporary_failures(scheduler, session, make_user, fake) -> None:
    """Exhausting every backoff attempt with a temporary error still moves the series on,
    never fails it — this pins `tz=user.timezone` on the temporary-failure `schedule_retry`
    call inside `deliver_reminders`."""
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    moment = NOW
    for _ in range(reminders.MAX_FAILURES):
        fake.errors.append(TelegramServerError(method=METHOD, message="Bad Gateway"))
        await scheduler.deliver_reminders(moment)
        series = await reload(session, series)
        moment = series.next_attempt_at
    assert series.status == ReminderStatus.PENDING
    assert series.attempts == 0
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_survives_an_unexpected_rendering_error(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    """Same as above, but through the `except Exception` path (e.g. a formatting bug) —
    pins `tz=user.timezone` on that call site's `schedule_retry` too."""
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "reminder_text", broken)
    moment = NOW
    for _ in range(reminders.MAX_FAILURES):
        await scheduler.deliver_reminders(moment)
        series = await reload(session, series)
        moment = series.next_attempt_at
    assert series.status == ReminderStatus.PENDING
    assert series.attempts == 0
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_the_digest_lists_todays_firing_of_a_repeat(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="08:00")
    at_0800 = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)
    rule = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 9, 28))
    await reminders.create_repeating(session, user, "таблетки", rule, at_0800)
    await session.commit()
    assert await scheduler.send_digests(at_0800) == 1
    assert "• 21:00 — таблетки" in fake.sent_texts()[0]
