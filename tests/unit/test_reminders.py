from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.models import Reminder, ReminderStatus
from assistant.core.services import reminders

NOW_LOCAL = datetime(2026, 9, 28, 15, 0)  # naive local wall time (Moscow)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # the same moment in UTC


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("18:30", datetime(2026, 9, 28, 18, 30)),
        ("14:00", datetime(2026, 9, 29, 14, 0)),  # already past today → tomorrow
        ("15:00", datetime(2026, 9, 29, 15, 0)),  # exactly now → tomorrow
        ("7:5", datetime(2026, 9, 29, 7, 5)),
        ("25.09 18:30", datetime(2026, 9, 25, 18, 30)),
        ("25.09.2027 18:30", datetime(2027, 9, 25, 18, 30)),
        ("29.02.2028 10:00", datetime(2028, 2, 29, 10, 0)),
        ("24:00", None),
        ("31.02 10:00", None),
        ("29.02.2027 10:00", None),
        ("abc", None),
        ("", None),
        ("1 2 3", None),
        ("25.09", None),
    ],
)
def test_parse_when(text: str, expected: datetime | None) -> None:
    assert reminders.parse_when(text, NOW_LOCAL.replace(tzinfo=None)) == expected


async def test_create_stores_utc(session, make_user) -> None:
    user = await make_user(tz="Asia/Vladivostok")
    reminder = await reminders.create(
        session, user, " встреча ", datetime(2026, 9, 29, 9, 0), now=NOW
    )
    assert reminder.text == "встреча"
    assert reminder.due_at == datetime(2026, 9, 28, 23, 0, tzinfo=UTC)
    assert reminder.next_attempt_at == reminder.due_at and reminder.status == ReminderStatus.PENDING


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


def test_retry_backoff_then_failure() -> None:
    reminder = _reminder()
    delays = []
    for _ in range(5):
        reminders.schedule_retry(reminder, NOW, "network")
        delays.append((reminder.next_attempt_at - NOW).total_seconds())
    assert delays == [30, 60, 300, 900, 3600] and reminder.status == ReminderStatus.PENDING
    reminders.schedule_retry(reminder, NOW, "network")
    assert reminder.status == ReminderStatus.FAILED and reminder.attempts == 6


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
