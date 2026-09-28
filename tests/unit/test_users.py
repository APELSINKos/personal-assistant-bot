from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from assistant.core.errors import InvalidInput
from assistant.core.models import Reminder, ReminderStatus
from assistant.core.services import users

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


async def test_ensure_creates_with_defaults(session) -> None:
    user = await users.ensure(session, 7, "Alex", "ru")
    assert (user.city, user.timezone, user.morning_time, user.morning_enabled) == (
        "Москва",
        "Europe/Moscow",
        "08:00",
        True,
    )
    assert user.language is None and user.tg_language == "ru" and not user.bot_blocked


async def test_ensure_unblocks_and_expires_old_reminders(session, make_user) -> None:
    await make_user(id=5, bot_blocked=True)
    old = NOW - timedelta(days=2)
    fresh = NOW - timedelta(hours=1)
    session.add_all(
        [
            Reminder(user_id=5, text="old", due_at=old, next_attempt_at=old),
            Reminder(user_id=5, text="fresh", due_at=fresh, next_attempt_at=fresh),
        ]
    )
    await session.commit()
    user = await users.ensure(session, 5, "Test", "ru", now=NOW)
    await session.commit()
    assert not user.bot_blocked
    statuses = {
        r.text: (r.status, r.last_error) for r in (await session.scalars(select(Reminder))).all()
    }
    assert statuses == {
        "old": (ReminderStatus.FAILED, "expired"),
        "fresh": (ReminderStatus.PENDING, None),
    }


async def test_set_morning_validates_time(session, make_user) -> None:
    user = await make_user()
    await users.set_morning(session, user, time="7:5", enabled=False)
    assert (user.morning_time, user.morning_enabled) == ("07:05", False)
    with pytest.raises(InvalidInput):
        await users.set_morning(session, user, time="25:00")


async def test_set_language_validates(session, make_user) -> None:
    user = await make_user()
    await users.set_language(session, user, "en")
    assert user.language == "en"
    await users.set_language(session, user, None)
    assert user.language is None
    with pytest.raises(InvalidInput):
        await users.set_language(session, user, "de")


async def test_set_city_rejects_unknown_zone(session, make_user) -> None:
    user = await make_user()
    with pytest.raises(InvalidInput):
        await users.set_city(session, user, "Марс", 0, 0, "Mars/Base")
