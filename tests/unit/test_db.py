from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from assistant.core.models import Note, Reminder, ReminderStatus


async def test_pragmas_applied(session) -> None:
    assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
    assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
    assert (await session.execute(text("PRAGMA busy_timeout"))).scalar() == 5000


async def test_user_delete_cascades(session, make_user) -> None:
    user = await make_user()
    session.add(Note(user_id=user.id, text="hello"))
    await session.commit()
    await session.delete(user)
    await session.commit()
    assert (await session.execute(select(Note))).scalars().all() == []


async def test_utc_datetime_roundtrip(session, make_user) -> None:
    user = await make_user()
    due = datetime(2026, 9, 28, 15, 30, tzinfo=UTC)
    session.add(Reminder(user_id=user.id, text="x", due_at=due, next_attempt_at=due))
    await session.commit()
    session.expunge_all()
    stored = (await session.execute(select(Reminder))).scalar_one()
    assert stored.due_at == due and stored.due_at.tzinfo is not None
    assert stored.status == ReminderStatus.PENDING and stored.attempts == 0
    assert isinstance(stored.status, ReminderStatus)


async def test_naive_datetime_rejected(session, make_user) -> None:
    user = await make_user()
    naive = datetime(2026, 9, 28, 15, 30)
    session.add(Reminder(user_id=user.id, text="x", due_at=naive, next_attempt_at=naive))
    with pytest.raises(StatementError):
        await session.commit()
