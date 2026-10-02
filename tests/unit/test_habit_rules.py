from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import Habit, HabitMark
from assistant.core.services import habits

TODAY = date(2026, 9, 28)  # a Monday
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow, same local date
WED = date(2026, 9, 30)  # Wednesday of this week
WED_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
LONG_AGO = date(2026, 8, 3)  # a Monday


def d(back: int) -> date:
    return TODAY - timedelta(days=back)


def week_of(monday: date, *weekdays: int) -> dict[date, bool]:
    """Done on the given weekdays (0 = Monday) of the week that starts on `monday`."""
    return {monday + timedelta(days=weekday): True for weekday in weekdays}


@pytest.mark.parametrize(
    ("marks", "goal", "created_on", "expected"),
    [
        # 3 a week met for the last two weeks, not the one before; this week has just begun
        (week_of(d(7), 0, 2, 4) | week_of(d(14), 1, 3, 5) | week_of(d(21), 0, 1), 3, LONG_AGO, 2),
        # this week's goal is already met by Wednesday: it counts too
        (week_of(d(0), 0, 1, 2) | week_of(d(7), 0, 2, 4), 3, LONG_AGO, 2),
        # rest days never break it: one day a week is enough for 1 a week
        (week_of(d(7), 6) | week_of(d(14), 0) | week_of(d(21), 3), 1, LONG_AGO, 3),
        # a missed week breaks it
        (week_of(d(7), 0, 1) | week_of(d(14), 0) | week_of(d(21), 0, 1), 2, LONG_AGO, 1),
        # created on Thursday 24 September with 5 a week: that first week asks for its 4 days
        (week_of(d(7), 3, 4, 5, 6), 5, date(2026, 9, 24), 1),
        # created this week, goal not met yet: nothing to count
        (week_of(d(0), 0), 2, TODAY, 0),
    ],
)
def test_weekly_streak(marks: dict[date, bool], goal: int, created_on: date, expected: int) -> None:
    assert habits.weekly_streak(marks, goal, created_on, WED) == expected


FOUR_WEEKS = week_of(d(28), 0, 1, 2) | week_of(d(21), 0, 1, 2) | week_of(d(14), 0, 1)
FOUR_WEEKS |= week_of(d(7), 4, 5, 6)


@pytest.mark.parametrize(
    ("marks", "goal", "created_on", "today", "expected"),
    [
        # daily, 10 days old, 6 done: 60 %
        ({d(back): True for back in (0, 1, 2, 4, 6, 9)}, 7, d(9), TODAY, 60),
        # daily, 1 day of 8 done: 12.5 % rounds up to 13
        ({d(0): True}, 7, d(7), TODAY, 13),
        # daily, done every day for 400 days: the window holds 365 of them
        ({d(back): True for back in range(400)}, 7, d(399), TODAY, 100),
        # daily, done the 41 days before today, today not marked yet: nothing missed, 100 %
        ({d(back): True for back in range(1, 42)}, 7, d(41), TODAY, 100),
        # the same with today marked missed: today counts, 41 of 42
        ({d(back): True for back in range(1, 42)} | {d(0): False}, 7, d(41), TODAY, 98),
        # one day missed in a full year: 364 of 365 is not 100 %
        ({d(back): back != 364 for back in range(400)}, 7, d(399), TODAY, 99),
        # one day done in 300: not 0 %
        ({d(0): True}, 7, d(299), TODAY, 1),
        # 3 a week, four weeks old: 3 of the 4 finished weeks met, this week not yet: 75 %
        (FOUR_WEEKS, 3, d(28), WED, 75),
        # the same with this week's goal met by Wednesday: it counts, 4 of 5
        (FOUR_WEEKS | week_of(d(0), 0, 1, 2), 3, d(28), WED, 80),
        ({}, 3, TODAY, TODAY, 0),
    ],
)
def test_year_percent(
    marks: dict[date, bool], goal: int, created_on: date, today: date, expected: int
) -> None:
    assert habits.year_percent(marks, goal, created_on, today) == expected


def test_year_map_covers_53_weeks_from_a_monday() -> None:
    habit = Habit(name="Спорт", created_on=d(2), weekly_goal=7)
    start, cells = habits.year_map(habit, {d(2): True, d(1): False}, TODAY)
    assert start == date(2025, 9, 29)  # the Monday 52 weeks before this week's
    assert len(cells) == 53 * 7
    # before the habit, then d(2) done, d(1) missed, today unmarked, the rest of this week ahead
    assert cells[-10:] == "." + "1" + "0" + "-" + "." * 6
    assert set(cells[:-10]) == {"."}


async def test_stats_of_a_weekly_habit(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Бег", created_on=LONG_AGO, weekly_goal=3)
    session.add(habit)
    await session.flush()
    marks = week_of(d(7), 0, 2, 4) | week_of(d(14), 1, 3, 5) | week_of(d(0), 0, 2)
    marks[d(0) + timedelta(days=1)] = False
    for day, done in marks.items():
        session.add(HabitMark(habit_id=habit.id, day=day, done=done))
    await session.commit()
    [stats] = await habits.list_with_stats(session, user, WED_NOW)
    assert (stats.unit, stats.streak, stats.record) == ("weeks", 2, 2)
    assert (stats.week_done, stats.week_goal) == (2, 3)
    assert stats.week == "101...."  # Monday done, Tuesday missed, Wednesday (today) done


async def test_record_outlives_a_broken_streak(session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Вода", created_on=d(30))
    session.add(habit)
    await session.flush()
    for back in [*range(20, 30), 1, 0]:  # ten days in a row long ago, then two now
        session.add(HabitMark(habit_id=habit.id, day=d(back), done=True))
    await session.commit()
    [stats] = await habits.list_with_stats(session, user, NOW)
    assert (stats.unit, stats.streak, stats.record) == ("days", 2, 10)
    assert (stats.week_done, stats.week_goal, stats.week) == (1, 7, "1......")


async def test_detail_has_the_year_map(session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Чтение", NOW)
    await habits.set_mark(session, user, habit.id, TODAY, True, NOW)
    detail = await habits.detail(session, user, habit.id, NOW)
    assert detail.stats.streak == 1
    assert detail.year_start == date(2025, 9, 29)
    assert detail.year.endswith("1" + "." * 6)


async def test_create_with_a_look_and_a_goal(session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Бег", NOW, emoji="🏃", color="sky", weekly_goal=3)
    assert (habit.emoji, habit.color, habit.weekly_goal) == ("🏃", "sky", 3)
    with pytest.raises(InvalidInput):
        await habits.create(session, user, "Ещё", NOW, emoji="🦄")
    with pytest.raises(InvalidInput):
        await habits.create(session, user, "Ещё", NOW, color="red")
    for goal in (0, 8):
        with pytest.raises(InvalidInput):
            await habits.create(session, user, "Ещё", NOW, weekly_goal=goal)


async def test_update_changes_name_look_and_goal(session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Бег", NOW)
    await habits.create(session, user, "Вода", NOW)
    stats = await habits.update(session, user, habit.id, NOW, name=" бег ")  # its own name: fine
    assert stats.habit.name == "бег"
    with pytest.raises(InvalidInput):
        await habits.update(session, user, habit.id, NOW, name="вода")  # another habit's name
    with pytest.raises(InvalidInput):
        await habits.update(session, user, habit.id, NOW, emoji="🦄")
    with pytest.raises(InvalidInput):
        await habits.update(session, user, habit.id, NOW, color="red")
    with pytest.raises(InvalidInput):
        await habits.update(session, user, habit.id, NOW, weekly_goal=9)
    stats = await habits.update(
        session, user, habit.id, NOW, emoji="🏃", color="coral", weekly_goal=4
    )
    assert (stats.habit.emoji, stats.habit.color, stats.habit.weekly_goal) == ("🏃", "coral", 4)
    assert (stats.unit, stats.week_goal) == ("weeks", 4)
    stranger = await make_user(id=2)
    with pytest.raises(NotFound):
        await habits.update(session, stranger, habit.id, NOW, name="x")


def test_pick_best_weighs_weeks_as_seven_days() -> None:
    daily = habits.HabitStats(
        habit=Habit(name="Вода", weekly_goal=7),
        done_today=True,
        streak=13,
        done_days=13,
        total_days=13,
        last_days=(True,) * 9,
        record=13,
        percent=100,
        week_done=1,
        week_goal=7,
        week="1......",
    )
    weekly = replace(daily, habit=Habit(name="Бег", weekly_goal=1), streak=2)
    assert habits.pick_best([daily, weekly]) == habits.Streak("Бег", 2, "weeks")  # 14 days' worth
    assert habits.pick_best([daily, replace(weekly, streak=1)]) == habits.Streak("Вода", 13, "days")
    assert habits.pick_best([replace(daily, streak=0)]) is None


async def test_best_streak_weighs_weeks_as_seven_days(session, make_user) -> None:
    user = await make_user()
    daily = Habit(user_id=user.id, name="Вода", created_on=LONG_AGO)
    weekly = Habit(user_id=user.id, name="Бег", created_on=LONG_AGO, weekly_goal=1)
    session.add_all([daily, weekly])
    await session.flush()
    for back in range(10):  # 10 days in a row
        session.add(HabitMark(habit_id=daily.id, day=d(back), done=True))
    for back in (7, 14):  # one day in each of the last two weeks: worth 14 days
        session.add(HabitMark(habit_id=weekly.id, day=d(back), done=True))
    await session.commit()
    assert await habits.best_streak(session, user, NOW) == habits.Streak("Бег", 2, "weeks")


def test_new_year_and_a_leap_february_are_weeks_like_any_other() -> None:
    # Thursday 2 March 2028, after a leap February; done every day since Monday 27 December
    # 2027, whose week holds a New Year
    today, began = date(2028, 3, 2), date(2027, 12, 27)
    every_day = {began + timedelta(days=back): True for back in range((today - began).days + 1)}
    assert habits.calc_streak(every_day, today) == 67  # 5 days of 2027, then 31 + 29 + 2
    assert habits.weekly_streak(every_day, 3, began, today) == 10  # 9 whole weeks and this one
    assert habits.year_percent(every_day, 7, began, today) == 100
    assert habits.year_percent(every_day, 3, began, today) == 100
    start, year = habits.year_map(Habit(created_on=began, weekly_goal=7), every_day, today)
    assert start == date(2027, 3, 1)  # the Monday 52 weeks before this week's
    assert year.count("1") == 67
    assert year.endswith("1111...")  # Monday to Thursday done, Friday to Sunday ahead
