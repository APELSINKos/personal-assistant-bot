from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from assistant.core.models import (
    Habit,
    JobRun,
    Lesson,
    LessonAlert,
    MireaGroup,
    Note,
    NoteItem,
    Reminder,
    ReminderStatus,
    Repeat,
    ScheduleKind,
    ScheduleSource,
    ShareCard,
    User,
    WeatherCity,
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


async def test_a_new_habit_gets_the_default_look_and_goal(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 10, 1))
    session.add(habit)
    await session.commit()
    assert (habit.emoji, habit.color, habit.weekly_goal) == ("🎯", "mint", 7)


async def test_share_cards_go_with_their_habit(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 10, 1))
    session.add(habit)
    await session.flush()
    session.add(
        ShareCard(token="t" * 43, user_id=user.id, habit_id=habit.id, image=b"jpeg", expires_at=T0)
    )
    await session.commit()
    await session.execute(delete(Habit).where(Habit.id == habit.id))
    await session.commit()
    assert (await session.scalars(select(ShareCard))).all() == []


async def test_weekly_goal_must_be_between_1_and_7(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 10, 1), weekly_goal=8)
    session.add(habit)
    with pytest.raises(IntegrityError):
        await session.commit()


def tula(user_id: int = 1, **fields: object) -> WeatherCity:
    values: dict[str, object] = {
        "user_id": user_id,
        "name": "Тула",
        "admin": "Тульская область",
        "country": "Россия",
        "lat": 54.19,
        "lon": 37.62,
        "timezone": "Europe/Moscow",
        "geo_id": 480562,
    }
    values.update(fields)
    return WeatherCity(**values)


async def test_a_new_note_is_not_pinned_and_its_items_are_not_done(session, make_user) -> None:
    user = await make_user()
    note = Note(user_id=user.id, text="Покупки")
    session.add(note)
    await session.flush()
    item = NoteItem(note_id=note.id, text="молоко")
    session.add(item)
    await session.commit()
    note_id, item_id = note.id, item.id
    session.expire_all()
    stored_note = await session.get(Note, note_id)
    stored_item = await session.get(NoteItem, item_id)
    assert stored_note is not None and stored_note.pinned_at is None
    assert stored_item is not None and stored_item.done is False
    assert stored_item.created_at.tzinfo is UTC


async def test_an_item_written_without_done_is_not_done(session, make_user) -> None:
    # The column's own default: a write that names no `done` (raw SQL, an old script) is open.
    user = await make_user()
    note = Note(user_id=user.id, text="Покупки")
    session.add(note)
    await session.commit()
    await session.execute(
        text(
            "INSERT INTO note_items (note_id, text, created_at) "
            "VALUES (:note, 'хлеб', '2026-10-05 10:00:00.000000')"
        ),
        {"note": note.id},
    )
    await session.commit()
    assert (await session.scalars(select(NoteItem.done))).all() == [False]


async def test_items_go_with_their_note(session, make_user) -> None:
    user = await make_user()
    note = Note(user_id=user.id, text="Покупки")
    session.add(note)
    await session.flush()
    session.add_all(
        [NoteItem(note_id=note.id, text="молоко"), NoteItem(note_id=note.id, text="хлеб")]
    )
    await session.commit()
    await session.execute(delete(Note).where(Note.id == note.id))
    await session.commit()
    assert (await session.scalars(select(NoteItem))).all() == []


async def test_ids_of_deleted_items_and_cities_never_come_back(session, make_user) -> None:
    # An old card's button carries the id of an item or a city: it must never reach a newer one.
    user = await make_user()
    note = Note(user_id=user.id, text="Покупки")
    session.add(note)
    await session.flush()
    item, city = NoteItem(note_id=note.id, text="молоко"), tula(user.id)
    session.add_all([item, city])
    await session.commit()
    gone_item, gone_city = item.id, city.id
    await session.execute(delete(NoteItem))
    await session.execute(delete(WeatherCity))
    await session.commit()
    again_item, again_city = NoteItem(note_id=note.id, text="молоко"), tula(user.id)
    session.add_all([again_item, again_city])
    await session.commit()
    assert again_item.id > gone_item and again_city.id > gone_city


async def test_cities_go_with_their_user(session, make_user) -> None:
    user = await make_user()
    session.add(tula(user.id))
    await session.commit()
    await session.delete(user)
    await session.commit()
    assert (await session.scalars(select(WeatherCity))).all() == []


@pytest.mark.parametrize(
    "coordinates", [{"lat": 90.5}, {"lat": -91.0}, {"lon": 180.5}, {"lon": -181.0}]
)
async def test_a_city_outside_the_coordinate_ranges_is_refused(
    session, make_user, coordinates
) -> None:
    user = await make_user()
    session.add(tula(user.id, **coordinates))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_the_edges_of_the_coordinates_are_allowed(session, make_user) -> None:
    user = await make_user()
    session.add_all(
        [
            tula(user.id, lat=90.0, lon=180.0, geo_id=1),
            tula(user.id, lat=-90.0, lon=-180.0, geo_id=2),
        ]
    )
    await session.commit()
    assert len((await session.scalars(select(WeatherCity))).all()) == 2


async def test_a_geonames_city_is_added_once_per_user(session, make_user) -> None:
    first, second = await make_user(1), await make_user(2)
    # Without an id the database cannot tell two cities apart (NULLs never clash): the service
    # compares their coordinates instead.
    session.add_all(
        [tula(first.id), tula(second.id), tula(first.id, geo_id=None), tula(first.id, geo_id=None)]
    )
    await session.commit()
    session.add(tula(first.id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
