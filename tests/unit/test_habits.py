from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Habit, HabitMark
from assistant.core.services import habits

TODAY = date(2026, 9, 28)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow, same local date


def d(back: int) -> date:
    return TODAY - timedelta(days=back)


@pytest.mark.parametrize(
    ("marks", "expected"),
    [
        ({d(i): True for i in range(5)}, 5),  # five in a row including today
        ({d(i): True for i in range(1, 5)}, 4),  # today not marked yet
        ({d(0): False, d(1): True, d(2): True}, 0),  # skipped today
        ({d(0): True, d(1): True, d(3): True}, 2),  # gap two days ago
        ({}, 0),
    ],
)
def test_calc_streak(marks: dict[date, bool], expected: int) -> None:
    assert habits.calc_streak(marks, TODAY) == expected


async def test_stats_example_12_of_17(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=d(16))
    session.add(habit)
    await session.flush()
    for back in [0, 1, 2, 3, 4, 6, 7, 9, 10, 12, 13, 15]:
        session.add(HabitMark(habit_id=habit.id, day=d(back), done=True))
    session.add(HabitMark(habit_id=habit.id, day=d(5), done=False))
    await session.commit()
    [stats] = await habits.list_with_stats(session, user, NOW)
    assert (stats.done_days, stats.total_days, stats.streak, stats.done_today) == (12, 17, 5, True)
    # last 9 days, oldest first: d(8) no mark, d(7) done, d(6) done, d(5) skipped, d(4)…d(0) done
    assert stats.last_days == (None, True, True, False, True, True, True, True, True)


async def test_create_rules(session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "  Спорт ", NOW)
    assert (habit.name, habit.created_on) == ("Спорт", TODAY)
    with pytest.raises(InvalidInput):
        await habits.create(session, user, "спорт", NOW)  # duplicate, case-insensitive
    with pytest.raises(InvalidInput):
        await habits.create(session, user, "x" * 51, NOW)
    for i in range(9):
        await habits.create(session, user, f"h{i}", NOW)
    with pytest.raises(LimitReached):
        await habits.create(session, user, "eleventh", NOW)


async def test_set_mark_range_and_toggle(session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Вода", NOW)
    stats = await habits.set_mark(session, user, habit.id, TODAY, True, NOW)
    assert (stats.done_today, stats.streak) == (True, 1)
    stats = await habits.set_mark(session, user, habit.id, TODAY, False, NOW)
    assert (stats.done_today, stats.streak) == (False, 0)
    stats = await habits.set_mark(session, user, habit.id, TODAY, None, NOW)
    assert stats.done_today is None
    with pytest.raises(InvalidInput):
        await habits.set_mark(session, user, habit.id, TODAY + timedelta(days=1), True, NOW)
    with pytest.raises(InvalidInput):
        await habits.set_mark(session, user, habit.id, TODAY - timedelta(days=1), True, NOW)


async def test_foreign_habit(session, make_user) -> None:
    owner = await make_user(id=1)
    stranger = await make_user(id=2)
    habit = await habits.create(session, owner, "Чтение", NOW)
    with pytest.raises(NotFound):
        await habits.set_mark(session, stranger, habit.id, TODAY, True, NOW)
    assert await habits.delete(session, 2, habit.id) is False
    assert await habits.delete(session, 1, habit.id) is True


async def test_progress_and_best_streak(session, make_user) -> None:
    user = await make_user()
    a = await habits.create(session, user, "A", NOW)
    await habits.create(session, user, "B", NOW)
    assert await habits.best_streak(session, user, NOW) is None
    await habits.set_mark(session, user, a.id, TODAY, True, NOW)
    assert await habits.today_progress(session, user, NOW) == (1, 2)
    assert await habits.best_streak(session, user, NOW) == habits.Streak("A", 1, "days")
