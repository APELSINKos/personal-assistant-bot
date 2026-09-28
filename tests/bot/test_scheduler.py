from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage
from sqlalchemy import select

from assistant.bot.scheduler import Scheduler
from assistant.core.models import FsmState, Reminder, ReminderStatus
from assistant.core.services import reminders

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


async def test_network_errors_back_off_then_fail(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    moment = NOW
    for attempt, delay in enumerate(reminders.BACKOFF, start=1):
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
            assert reminder.next_attempt_at == moment + timedelta(seconds=delay)
            moment = reminder.next_attempt_at
    assert reminder.status == ReminderStatus.FAILED


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


async def test_english_reminder(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False, language="en")
    await add_reminder(session, ago=timedelta(minutes=30), text="call mom")
    await scheduler.deliver_reminders(NOW)
    assert fake.sent_texts() == ["⏰ Reminder: call mom (was due at 14:30)"]
