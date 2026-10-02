"""Habits: daily marks, statistics and streaks (dates are the user's local dates).

A habit has a weekly goal of 1–7 days. With 7 it is a daily habit and its streak counts days in a
row; with fewer it counts weeks in a row whose goal was met, so rest days never break it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, NamedTuple

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.habit_style import COLORS, DAILY, DEFAULT_COLOR, DEFAULT_EMOJI, EMOJI
from assistant.core.models import Habit, HabitMark, User
from assistant.core.timeutil import local_today

LAST_DAYS = 9
YEAR_DAYS = 365  # the window of «за год»
YEAR_WEEKS = 53  # the year map: this week and the 52 before it

StreakUnit = Literal["days", "weeks"]

# One character per day in the year map and the week strip.
DONE, MISSED, UNMARKED, OUTSIDE = "1", "0", "-", "."


@dataclass(frozen=True)
class HabitStats:
    habit: Habit
    done_today: bool | None
    streak: int
    done_days: int
    total_days: int
    last_days: tuple[bool | None, ...]
    record: int
    percent: int
    week_done: int
    week_goal: int
    week: str  # Monday to Sunday of this week, one character per day

    @property
    def unit(self) -> StreakUnit:
        return streak_unit(self.habit)


@dataclass(frozen=True)
class HabitDetail:
    stats: HabitStats
    year_start: date  # the Monday YEAR_WEEKS - 1 weeks before this week's
    year: str  # YEAR_WEEKS * 7 characters from year_start


class Streak(NamedTuple):
    name: str
    length: int  # in `unit`
    unit: StreakUnit


def streak_unit(habit: Habit) -> StreakUnit:
    return "days" if habit.weekly_goal == DAILY else "weeks"


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def calc_streak(marks: Mapping[date, bool], today: date) -> int:
    day = today if marks.get(today) is not None else today - timedelta(days=1)
    streak = 0
    while marks.get(day) is True:
        streak += 1
        day -= timedelta(days=1)
    return streak


def week_goal(goal: int, week_start: date, first: date) -> int:
    """The goal of the week starting on `week_start`: a week that `first` (the habit's first
    day, or the start of a window) cuts asks only for the days it has left."""
    return min(goal, 7 - max((first - week_start).days, 0))


def _done_in_week(marks: Mapping[date, bool], week_start: date, first: date) -> int:
    return sum(
        1
        for offset in range(7)
        if (day := week_start + timedelta(days=offset)) >= first and marks.get(day) is True
    )


def _week_met(marks: Mapping[date, bool], week_start: date, goal: int, first: date) -> bool:
    return _done_in_week(marks, week_start, first) >= week_goal(goal, week_start, first)


def weekly_streak(marks: Mapping[date, bool], goal: int, created_on: date, today: date) -> int:
    """Weeks in a row whose goal was met, up to this week if its goal is met already —
    otherwise up to last week: a week that is still going never breaks the streak."""
    week = monday(today)
    if not _week_met(marks, week, goal, created_on):
        week -= timedelta(weeks=1)
    streak = 0
    while week >= monday(created_on) and _week_met(marks, week, goal, created_on):
        streak += 1
        week -= timedelta(weeks=1)
    return streak


def _daily_record(marks: Mapping[date, bool]) -> int:
    best = run = 0
    previous: date | None = None
    for day in sorted(day for day, done in marks.items() if done):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best


def _weekly_record(marks: Mapping[date, bool], goal: int, created_on: date, today: date) -> int:
    best = run = 0
    week = monday(created_on)
    while week <= monday(today):
        if _week_met(marks, week, goal, created_on):
            run += 1
            best = max(best, run)
        elif week < monday(today):  # this week, still going, does not end a run
            run = 0
        week += timedelta(weeks=1)
    return best


def _share(part: int, whole: int) -> int:
    """part / whole in whole percent, halves rounded up; 0 for an empty whole. 100 only when
    nothing is missing and 0 only when nothing is done: 364 of 365 is 99, 1 of 300 is 1."""
    if not whole:
        return 0
    rounded = (200 * part + whole) // (2 * whole)
    if part < whole:
        rounded = min(rounded, 99)
    if part > 0:
        rounded = max(rounded, 1)
    return rounded


def year_percent(marks: Mapping[date, bool], goal: int, created_on: date, today: date) -> int:
    """Done days (daily habit) or met weeks (weekly habit) over the last YEAR_DAYS days, never
    before the habit began. Today counts once it is marked; weeks count once they are over, this
    week only once its goal is met."""
    first = max(created_on, today - timedelta(days=YEAR_DAYS - 1))
    if goal == DAILY:
        # Like the streak, today counts once it is marked: an unmarked today is not a miss yet.
        last = today if marks.get(today) is not None else today - timedelta(days=1)
        done = sum(1 for day, mark in marks.items() if mark and first <= day <= last)
        return _share(done, max((last - first).days + 1, 0))
    met = counted = 0
    week = monday(first)
    while week <= monday(today):
        ok = _week_met(marks, week, goal, first)
        if ok or week < monday(today):
            counted += 1
            met += ok
        week += timedelta(weeks=1)
    return _share(met, counted)


def _cell(marks: Mapping[date, bool], day: date, created_on: date, today: date) -> str:
    if not created_on <= day <= today:
        return OUTSIDE
    mark = marks.get(day)
    return UNMARKED if mark is None else DONE if mark else MISSED


def year_map(habit: Habit, marks: Mapping[date, bool], today: date) -> tuple[date, str]:
    start = monday(today) - timedelta(weeks=YEAR_WEEKS - 1)
    cells = (
        _cell(marks, start + timedelta(days=offset), habit.created_on, today)
        for offset in range(YEAR_WEEKS * 7)
    )
    return start, "".join(cells)


def _stats(habit: Habit, marks: Mapping[date, bool], today: date) -> HabitStats:
    goal = habit.weekly_goal
    this_week = monday(today)
    if goal == DAILY:
        streak = calc_streak(marks, today)
        record = _daily_record(marks)
    else:
        streak = weekly_streak(marks, goal, habit.created_on, today)
        record = _weekly_record(marks, goal, habit.created_on, today)
    return HabitStats(
        habit=habit,
        done_today=marks.get(today),
        streak=streak,
        done_days=sum(1 for done in marks.values() if done),
        total_days=max((today - habit.created_on).days + 1, 1),
        last_days=tuple(
            marks.get(today - timedelta(days=back)) for back in range(LAST_DAYS - 1, -1, -1)
        ),
        record=max(record, streak),
        percent=year_percent(marks, goal, habit.created_on, today),
        week_done=_done_in_week(marks, this_week, habit.created_on),
        week_goal=week_goal(goal, this_week, habit.created_on),
        week="".join(
            _cell(marks, this_week + timedelta(days=offset), habit.created_on, today)
            for offset in range(7)
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


async def detail(
    session: AsyncSession, user: User, habit_id: int, now: datetime | None = None
) -> HabitDetail:
    habit = await _owned(session, user.id, habit_id)
    marks = (await _marks(session, [habit.id]))[habit.id]
    today = local_today(user.timezone, now)
    start, year = year_map(habit, marks, today)
    return HabitDetail(stats=_stats(habit, marks, today), year_start=start, year=year)


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= LIMITS.habit_length:
        raise InvalidInput(field="name", reason="length", limit=LIMITS.habit_length)
    return cleaned


def _check_look(emoji: str, color: str, weekly_goal: int) -> None:
    if emoji not in EMOJI:
        raise InvalidInput(field="emoji", reason="invalid")
    if color not in COLORS:
        raise InvalidInput(field="color", reason="invalid")
    if not 1 <= weekly_goal <= DAILY:
        raise InvalidInput(field="weekly_goal", reason="out_of_range")


async def create(
    session: AsyncSession,
    user: User,
    name: str,
    now: datetime | None = None,
    *,
    emoji: str = DEFAULT_EMOJI,
    color: str = DEFAULT_COLOR,
    weekly_goal: int = DAILY,
) -> Habit:
    cleaned = _clean_name(name)
    _check_look(emoji, color, weekly_goal)
    existing = await _habits(session, user.id)
    if any(habit.name.casefold() == cleaned.casefold() for habit in existing):
        raise InvalidInput(field="name", reason="duplicate")
    if len(existing) >= LIMITS.habits:
        raise LimitReached(entity="habit", limit=LIMITS.habits)
    habit = Habit(
        user_id=user.id,
        name=cleaned,
        created_on=local_today(user.timezone, now),
        emoji=emoji,
        color=color,
        weekly_goal=weekly_goal,
    )
    session.add(habit)
    await session.flush()
    return habit


async def update(
    session: AsyncSession,
    user: User,
    habit_id: int,
    now: datetime | None = None,
    *,
    name: str | None = None,
    emoji: str | None = None,
    color: str | None = None,
    weekly_goal: int | None = None,
) -> HabitStats:
    """Change any of name, emoji, colour and weekly goal. A new goal recounts the whole
    history: the goals a habit had before are not kept."""
    habit = await _owned(session, user.id, habit_id)
    _check_look(
        habit.emoji if emoji is None else emoji,
        habit.color if color is None else color,
        habit.weekly_goal if weekly_goal is None else weekly_goal,
    )
    if name is not None:
        cleaned = _clean_name(name)
        others = [other for other in await _habits(session, user.id) if other.id != habit.id]
        if any(other.name.casefold() == cleaned.casefold() for other in others):
            raise InvalidInput(field="name", reason="duplicate")
        habit.name = cleaned
    if emoji is not None:
        habit.emoji = emoji
    if color is not None:
        habit.color = color
    if weekly_goal is not None:
        habit.weekly_goal = weekly_goal
    await session.flush()
    return await stats_for(session, user, habit.id, now)


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


def _days_worth(stats: HabitStats) -> int:
    return stats.streak * (1 if stats.unit == "days" else 7)


def pick_best(items: Iterable[HabitStats]) -> Streak | None:
    """The longest current streak, weeks weighed as 7 days each, in its own unit."""
    best: HabitStats | None = None
    for item in items:
        if item.streak > 0 and (best is None or _days_worth(item) > _days_worth(best)):
            best = item
    return None if best is None else Streak(best.habit.name, best.streak, best.unit)


async def best_streak(
    session: AsyncSession, user: User, now: datetime | None = None
) -> Streak | None:
    return pick_best(await list_with_stats(session, user, now))
