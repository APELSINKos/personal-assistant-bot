from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import phrases, reminders
from assistant.core.services.recurrence import Rule
from assistant.core.timeutil import to_local

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # the same moment in UTC


async def test_create_stores_utc(session, make_user) -> None:
    user = await make_user(tz="Asia/Vladivostok")
    reminder = await reminders.create(
        session, user, " встреча ", datetime(2026, 9, 29, 9, 0), now=NOW
    )
    assert reminder.text == "встреча"
    assert reminder.due_at == datetime(2026, 9, 28, 23, 0, tzinfo=UTC)
    assert reminder.next_attempt_at == reminder.due_at and reminder.status == ReminderStatus.PENDING


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 24, 23, 30, tzinfo=UTC),  # 01:30 CEST, the night the clocks go back
        datetime(2026, 3, 29, 0, 30, tzinfo=UTC),  # 01:30 CET, the night they go forward
    ],
    ids=["back", "forward"],
)
async def test_a_span_from_a_phrase_counts_real_time(session, make_user, now) -> None:
    user = await make_user(tz="Europe/Berlin")
    parsed = phrases.parse("через 2 часа позвонить", to_local(now, user.timezone))
    assert parsed is not None
    reminder = await reminders.create_from(session, user, parsed, now)
    assert reminder.due_at == now + timedelta(hours=2)


async def test_create_rejects_past_and_limits(session, make_user) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput):
        await reminders.create(session, user, "x", datetime(2026, 9, 28, 14, 59), now=NOW)
    with pytest.raises(InvalidInput):
        await reminders.create(session, user, "x" * 201, datetime(2026, 9, 29, 9, 0), now=NOW)
    for i in range(20):
        await reminders.create(session, user, f"r{i}", datetime(2026, 9, 29, 9, i), now=NOW)
    with pytest.raises(LimitReached):
        await reminders.create(session, user, "one more", datetime(2026, 9, 29, 10, 0), now=NOW)


async def test_pending_order_and_cancel_ownership(session, make_user) -> None:
    user = await make_user(id=1)
    await make_user(id=2)
    late = await reminders.create(session, user, "А", datetime(2026, 9, 28, 23, 0), now=NOW)
    await reminders.create(session, user, "Б", datetime(2026, 9, 28, 22, 0), now=NOW)
    assert [r.text for r in await reminders.pending(session, 1)] == ["Б", "А"]
    assert await reminders.cancel(session, 2, late.id) is False
    assert await reminders.cancel(session, 1, late.id) is True
    assert await reminders.cancel(session, 1, late.id) is False
    assert [r.text for r in await reminders.pending(session, 1)] == ["Б"]


async def test_due_skips_blocked_future_and_done(session, make_user) -> None:
    await make_user(id=1)
    await make_user(id=2, bot_blocked=True)
    past = NOW - timedelta(minutes=1)
    future = NOW + timedelta(minutes=1)
    session.add_all(
        [
            Reminder(user_id=1, text="due", due_at=past, next_attempt_at=past),
            Reminder(user_id=1, text="future", due_at=future, next_attempt_at=future),
            Reminder(
                user_id=1,
                text="sent",
                due_at=past,
                next_attempt_at=past,
                status=ReminderStatus.SENT,
            ),
            Reminder(user_id=2, text="blocked", due_at=past, next_attempt_at=past),
        ]
    )
    await session.commit()
    assert [r.text for r, _ in await reminders.due(session, NOW)] == ["due"]


def _reminder() -> Reminder:
    return Reminder(
        user_id=1,
        text="x",
        due_at=NOW,
        next_attempt_at=NOW,
        attempts=0,
        status=ReminderStatus.PENDING,
    )


def test_retry_backoff_then_failure(caplog) -> None:
    reminder = _reminder()
    reminder.id = 5
    delays = []
    for _ in range(6):
        reminders.schedule_retry(reminder, NOW, "network")
        delays.append((reminder.next_attempt_at - NOW).total_seconds())
    # Every delay is used, the 3 h one included; the 7th failure is the last one.
    assert delays == [30, 60, 300, 900, 3600, 10800] and reminder.status == ReminderStatus.PENDING
    assert reminders.MAX_FAILURES == 7 and not caplog.records
    reminders.schedule_retry(reminder, NOW, "network")
    assert reminder.status == ReminderStatus.FAILED and reminder.attempts == 7
    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert record.getMessage() == "reminder 5 gave up after 7 attempts: network"


def test_retry_after_does_not_count_attempt() -> None:
    reminder = _reminder()
    reminders.schedule_retry(reminder, NOW, "flood", retry_after=7)
    assert reminder.attempts == 0 and reminder.next_attempt_at == NOW + timedelta(seconds=7)


async def test_today_for_uses_user_zone(session, make_user) -> None:
    user = await make_user(tz="Asia/Vladivostok")  # UTC+10; local date at NOW is 28.09, 22:00
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    for local in (datetime(2026, 9, 28, 23, 30), datetime(2026, 9, 29, 0, 30)):
        await reminders.create(session, user, local.isoformat(), local, now=now)
    assert [r.text for r in await reminders.today_for(session, user, now)] == [
        "2026-09-28T23:30:00"
    ]
    assert len((await session.scalars(select(Reminder))).all()) == 2


async def test_create_rejects_a_moment_outside_the_calendar(session, make_user) -> None:
    user = await make_user(tz="America/New_York")
    with pytest.raises(InvalidInput) as error:
        await reminders.create(session, user, "x", datetime(9999, 12, 31, 23, 59), now=NOW)
    assert error.value.params["reason"] == "invalid"


async def test_today_for_includes_todays_firing_of_a_repeat(session, make_user) -> None:
    user = await make_user()  # Moscow
    morning = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)  # 08:00 in Moscow
    rule = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 9, 28))
    await reminders.create_repeating(session, user, "таблетки", rule, morning)
    assert [r.text for r in await reminders.today_for(session, user, morning)] == ["таблетки"]
