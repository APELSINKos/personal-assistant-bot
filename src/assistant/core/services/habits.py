"""Habits: daily marks, statistics and streaks (dates are the user's local dates)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Habit, HabitMark, User
from assistant.core.timeutil import local_today

LAST_DAYS = 9


@dataclass(frozen=True)
class HabitStats:
    habit: Habit
    done_today: bool | None
    streak: int
    done_days: int
    total_days: int
    last_days: tuple[bool | None, ...]


def calc_streak(marks: Mapping[date, bool], today: date) -> int:
    day = today if marks.get(today) is not None else today - timedelta(days=1)
    streak = 0
    while marks.get(day) is True:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _stats(habit: Habit, marks: Mapping[date, bool], today: date) -> HabitStats:
    return HabitStats(
        habit=habit,
        done_today=marks.get(today),
        streak=calc_streak(marks, today),
        done_days=sum(1 for done in marks.values() if done),
        total_days=max((today - habit.created_on).days + 1, 1),
        last_days=tuple(
            marks.get(today - timedelta(days=back)) for back in range(LAST_DAYS - 1, -1, -1)
        ),
    )


async def _habits(session: AsyncSession, user_id: int) -> list[Habit]:
    result = await session.scalars(select(Habit).where(Habit.user_id == user_id).order_by(Habit.id))
    return list(result.all())


async def _marks(session: AsyncSession, habit_ids: Sequence[int]) -> dict[int, dict[date, bool]]:
    marks: dict[int, dict[date, bool]] = {habit_id: {} for habit_id in habit_ids}
    if habit_ids:
        result = await session.scalars(select(HabitMark).where(HabitMark.habit_id.in_(habit_ids)))
        for mark in result.all():
            marks[mark.habit_id][mark.day] = mark.done
    return marks


async def list_with_stats(
    session: AsyncSession, user: User, now: datetime | None = None
) -> list[HabitStats]:
    today = local_today(user.timezone, now)
    items = await _habits(session, user.id)
    marks = await _marks(session, [habit.id for habit in items])
    return [_stats(habit, marks[habit.id], today) for habit in items]


async def _owned(session: AsyncSession, user_id: int, habit_id: int) -> Habit:
    habit = await session.scalar(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == user_id)
    )
    if habit is None:
        raise NotFound(entity="habit")
    return habit


async def stats_for(
    session: AsyncSession, user: User, habit_id: int, now: datetime | None = None
) -> HabitStats:
    habit = await _owned(session, user.id, habit_id)
    marks = await _marks(session, [habit.id])
    return _stats(habit, marks[habit.id], local_today(user.timezone, now))


async def create(
    session: AsyncSession, user: User, name: str, now: datetime | None = None
) -> Habit:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= LIMITS.habit_length:
        raise InvalidInput(field="name", reason="length", limit=LIMITS.habit_length)
    existing = await _habits(session, user.id)
    if any(habit.name.casefold() == cleaned.casefold() for habit in existing):
        raise InvalidInput(field="name", reason="duplicate")
    if len(existing) >= LIMITS.habits:
        raise LimitReached(entity="habit", limit=LIMITS.habits)
    habit = Habit(user_id=user.id, name=cleaned, created_on=local_today(user.timezone, now))
    session.add(habit)
    await session.flush()
    return habit


async def delete(session: AsyncSession, user_id: int, habit_id: int) -> bool:
    result = await session.execute(
        sql_delete(Habit).where(Habit.id == habit_id, Habit.user_id == user_id)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def set_mark(
    session: AsyncSession,
    user: User,
    habit_id: int,
    day: date,
    done: bool | None,
    now: datetime | None = None,
) -> HabitStats:
    habit = await _owned(session, user.id, habit_id)
    today = local_today(user.timezone, now)
    if not habit.created_on <= day <= today:
        raise InvalidInput(field="day", reason="out_of_range")
    existing = await session.get(HabitMark, (habit.id, day))
    if done is None:
        if existing is not None:
            await session.delete(existing)
    elif existing is None:
        session.add(HabitMark(habit_id=habit.id, day=day, done=done))
    else:
        existing.done = done
    await session.flush()
    return await stats_for(session, user, habit.id, now)


async def today_progress(
    session: AsyncSession, user: User, now: datetime | None = None
) -> tuple[int, int]:
    items = await list_with_stats(session, user, now)
    return sum(1 for item in items if item.done_today), len(items)


async def best_streak(
    session: AsyncSession, user: User, now: datetime | None = None
) -> tuple[str, int] | None:
    best: tuple[str, int] | None = None
    for item in await list_with_stats(session, user, now):
        if item.streak > 0 and (best is None or item.streak > best[1]):
            best = (item.habit.name, item.streak)
    return best
