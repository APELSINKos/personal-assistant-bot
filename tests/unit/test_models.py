from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from assistant.core.models import (
    JobRun,
    Lesson,
    LessonAlert,
    MireaGroup,
    Reminder,
    ReminderStatus,
    Repeat,
    ScheduleKind,
    ScheduleSource,
    User,
    WeekLabel,
)

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


T0 = datetime(2026, 9, 30, 9, 40, tzinfo=UTC)


async def test_schedule_tables_round_trip(session, make_user) -> None:
    user = await make_user()
    session.add_all(
        [
            MireaGroup(
                id=4805,
                name="ИКБО-63-24",
                name_key="икбо6324",
                semester_end=date(2026, 12, 31),
                seen_at=T0,
            ),
            ScheduleSource(
                user_id=user.id,
                kind=ScheduleKind.MIREA,
                mirea_id=4805,
                url="https://english.mirea.ru/schedule/api/ical/1/4805",
                title="ИКБО-63-24",
                fetched_at=T0,
                ok_at=T0,
                next_refresh_at=T0,
            ),
            Lesson(
                user_id=user.id,
                uid="75bb3b9e",
                starts_at=T0,
                ends_at=T0,
                title="Разработка баз данных",
                kind="ПР",
                room="И-212-б (В-78)",
            ),
            WeekLabel(
                user_id=user.id,
                start_date=date(2026, 9, 28),
                end_date=date(2026, 10, 5),
                label="5 неделя",
            ),
            LessonAlert(user_id=user.id, uid="75bb3b9e", starts_at=T0, sent_at=T0),
            JobRun(name="mirea_full", finished_at=T0, info="found 1500"),
        ]
    )
    await session.commit()
    session.expire_all()
    source = await session.get(ScheduleSource, 1)
    assert source is not None
    assert source.kind is ScheduleKind.MIREA and source.ok_at == T0 and source.body is None
    assert source.lesson_reminder_minutes is None and source.error is None
    lesson = (await session.scalars(select(Lesson))).one()
    assert lesson.starts_at == T0 and lesson.kind == "ПР"
    group = await session.get(MireaGroup, 4805)
    assert group is not None and group.semester_end == date(2026, 12, 31)


async def test_one_alert_per_lesson_start(session, make_user) -> None:
    user = await make_user()
    session.add(LessonAlert(user_id=user.id, uid="u", starts_at=T0, sent_at=T0))
    await session.commit()
    session.add(LessonAlert(user_id=user.id, uid="u", starts_at=T0, sent_at=T0))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_deleting_a_user_deletes_their_schedule(session, make_user) -> None:
    user = await make_user()
    session.add_all(
        [
            ScheduleSource(
                user_id=user.id,
                kind=ScheduleKind.FILE,
                body=b"BEGIN:VCALENDAR",
                fetched_at=T0,
                next_refresh_at=T0,
            ),
            Lesson(user_id=user.id, uid="u", starts_at=T0, ends_at=T0, title="x"),
            WeekLabel(
                user_id=user.id,
                start_date=date(2026, 9, 28),
                end_date=date(2026, 10, 5),
                label="5 неделя",
            ),
        ]
    )
    await session.commit()
    await session.delete(user)
    await session.commit()
    for model in (ScheduleSource, Lesson, WeekLabel):
        assert (await session.scalars(select(model))).all() == []
