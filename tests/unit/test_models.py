from __future__ import annotations

from datetime import UTC, datetime

from assistant.core.models import Reminder, ReminderStatus, Repeat, User

DUE = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


async def test_new_reminder_defaults(session, make_user) -> None:
    user = await make_user()
    reminder = Reminder(user_id=user.id, text="t", due_at=DUE, next_attempt_at=DUE)
    session.add(reminder)
    await session.commit()
    reminder_id, user_id = reminder.id, user.id
    session.expire_all()  # force a real reload: expire_on_commit=False keeps the cached object
    stored = await session.get(Reminder, reminder_id)
    assert stored.repeat is Repeat.NONE and stored.interval_weeks == 1
    assert stored.occurrence_at == DUE  # filled from due_at when not given
    assert stored.status is ReminderStatus.PENDING and stored.parent_id is None
    assert (await session.get(User, user_id)).can_write is False


async def test_weekly_repeat_round_trips(session, make_user) -> None:
    user = await make_user()
    reminder = Reminder(
        user_id=user.id,
        text="t",
        due_at=DUE,
        next_attempt_at=DUE,
        repeat=Repeat.WEEKLY,
        weekdays=31,
    )
    session.add(reminder)
    await session.commit()
    reminder_id = reminder.id
    session.expire_all()
    stored = await session.get(Reminder, reminder_id)
    assert stored.repeat is Repeat.WEEKLY and stored.weekdays == 31


async def test_done_status_round_trips(session, make_user) -> None:
    user = await make_user()
    reminder = Reminder(
        user_id=user.id, text="t", due_at=DUE, next_attempt_at=DUE, status=ReminderStatus.DONE
    )
    session.add(reminder)
    await session.commit()
    reminder_id = reminder.id  # read before expiring: AsyncSession can't lazy-refresh a plain attr
    session.expire_all()
    assert (await session.get(Reminder, reminder_id)).status is ReminderStatus.DONE


async def test_deleting_a_repeat_keeps_its_snoozed_copy(session, make_user) -> None:
    user = await make_user()
    parent = Reminder(user_id=user.id, text="p", due_at=DUE, next_attempt_at=DUE)
    session.add(parent)
    await session.flush()
    copy = Reminder(user_id=user.id, text="c", due_at=DUE, next_attempt_at=DUE, parent_id=parent.id)
    session.add(copy)
    await session.commit()
    await session.delete(parent)
    await session.commit()
    copy_id = copy.id  # read before expiring: AsyncSession can't lazy-refresh a plain attr
    session.expire_all()
    assert (await session.get(Reminder, copy_id)).parent_id is None
