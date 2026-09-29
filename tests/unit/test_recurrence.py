from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from assistant.core.errors import InvalidInput
from assistant.core.i18n import translator, weekday_short
from assistant.core.models import Repeat
from assistant.core.services.recurrence import (
    WEEKDAYS,
    WEEKENDS,
    Rule,
    between,
    describe,
    fires_on,
    latest_up_to,
    next_after,
)

MSK = "Europe/Moscow"
BERLIN = "Europe/Berlin"
MON = date(2026, 9, 28)  # a Monday
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow


def rule(repeat: Repeat, time: str = "09:00", anchor: date = MON, **kw) -> Rule:
    return Rule(repeat=repeat, time_local=time, anchor_date=anchor, **kw)


def utc(y, m, d, h=0, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


@pytest.mark.parametrize(
    ("r", "after", "expected"),
    [
        # daily: later today, then tomorrow once the time has passed
        (rule(Repeat.DAILY, "21:00"), NOW, utc(2026, 9, 28, 18)),
        (rule(Repeat.DAILY, "09:00"), NOW, utc(2026, 9, 29, 6)),
        (rule(Repeat.DAILY, "15:00"), NOW, utc(2026, 9, 29, 12)),  # exactly now → next day
        # weekdays: Friday evening → Monday
        (rule(Repeat.WEEKLY, weekdays=WEEKDAYS), utc(2026, 10, 2, 18), utc(2026, 10, 5, 6)),
        # weekends: from Monday → Saturday
        (rule(Repeat.WEEKLY, weekdays=WEEKENDS), NOW, utc(2026, 10, 3, 6)),
        # Tuesday and Thursday
        (rule(Repeat.WEEKLY, weekdays=2 | 8), NOW, utc(2026, 9, 29, 6)),
        (rule(Repeat.WEEKLY, weekdays=2 | 8), utc(2026, 9, 29, 7), utc(2026, 10, 1, 6)),
        # every other Wednesday, anchored on Wed 30.09: 30.09, then 14.10
        (
            rule(Repeat.WEEKLY, weekdays=4, interval_weeks=2, anchor=date(2026, 9, 30)),
            utc(2026, 9, 30, 7),
            utc(2026, 10, 14, 6),
        ),
        # every other Monday anchored on a Wednesday: the anchor's own Monday is before the
        # anchor, next week is the "off" week, so the first firing is the Monday after that
        (
            rule(Repeat.WEEKLY, weekdays=1, interval_weeks=2, anchor=date(2026, 9, 30)),
            NOW,
            utc(2026, 10, 12, 6),
        ),
        # monthly on the 5th
        (rule(Repeat.MONTHLY, "12:00", month_day=5), NOW, utc(2026, 10, 5, 9)),
        # monthly on the 31st → last day of short months
        (rule(Repeat.MONTHLY, "12:00", month_day=31), NOW, utc(2026, 9, 30, 9)),
        (rule(Repeat.MONTHLY, "12:00", month_day=31), utc(2026, 10, 1), utc(2026, 10, 31, 9)),
        (rule(Repeat.MONTHLY, "12:00", month_day=31), utc(2027, 2, 1), utc(2027, 2, 28, 9)),
        (rule(Repeat.MONTHLY, "12:00", month_day=29), utc(2028, 2, 1), utc(2028, 2, 29, 9)),
        # the anchor is respected: nothing before it
        (rule(Repeat.DAILY, anchor=date(2026, 10, 10)), NOW, utc(2026, 10, 10, 6)),
    ],
)
def test_next_after(r: Rule, after: datetime, expected: datetime) -> None:
    r.validate()
    assert next_after(r, after, MSK) == expected


def test_local_time_survives_dst() -> None:
    # Berlin switches to winter time on 25.10.2026: 09:00 is 07:00 UTC before, 08:00 after.
    r = rule(Repeat.DAILY, anchor=date(2026, 10, 20))
    assert next_after(r, utc(2026, 10, 24, 12), BERLIN) == utc(2026, 10, 25, 8)
    assert next_after(r, utc(2026, 10, 23, 12), BERLIN) == utc(2026, 10, 24, 7)


def test_time_inside_a_dst_gap_moves_forward() -> None:
    # 29.03.2026 02:30 does not exist in Berlin; it resolves to 03:30 local = 01:30 UTC.
    r = rule(Repeat.DAILY, "02:30", anchor=date(2026, 3, 1))
    assert next_after(r, utc(2026, 3, 28, 12), BERLIN) == utc(2026, 3, 29, 1, 30)


def test_zone_west_of_utc() -> None:
    # New York, 20:00 local on Monday = 00:00 UTC on Tuesday.
    r = rule(Repeat.WEEKLY, "20:00", weekdays=1)
    assert next_after(r, utc(2026, 9, 28, 12), "America/New_York") == utc(2026, 9, 29, 0)


def test_between_lists_firings_in_range() -> None:
    r = rule(Repeat.WEEKLY, "10:40", weekdays=2 | 8)
    got = between(r, utc(2026, 9, 28), utc(2026, 10, 5), MSK)
    assert got == [utc(2026, 9, 29, 7, 40), utc(2026, 10, 1, 7, 40)]


def test_between_respects_limit_and_anchor() -> None:
    r = rule(Repeat.DAILY, anchor=date(2026, 10, 1))
    got = between(r, utc(2026, 9, 1), utc(2026, 12, 31), MSK, limit=3)
    assert got == [utc(2026, 10, 1, 6), utc(2026, 10, 2, 6), utc(2026, 10, 3, 6)]


def test_between_covers_the_full_window_regardless_of_length() -> None:
    # Two years, well past the internal safety horizon: nothing gets silently dropped.
    r = rule(Repeat.DAILY, anchor=date(2026, 1, 1))
    got = between(r, utc(2026, 1, 1), utc(2028, 1, 1), MSK, limit=10_000)
    assert len(got) == 730
    assert got[0] == utc(2026, 1, 1, 6)
    assert got[-1] == utc(2027, 12, 31, 6)


def test_latest_up_to_skips_to_the_last_missed_firing() -> None:
    r = rule(Repeat.DAILY, "09:00")
    since = utc(2026, 9, 28, 6)
    assert latest_up_to(r, utc(2026, 10, 1, 12), since, MSK) == utc(2026, 10, 1, 6)
    assert latest_up_to(r, utc(2026, 9, 28, 7), since, MSK) == since


def test_latest_up_to_works_across_a_long_span() -> None:
    # ~500 days between `since` and `moment`, past the internal safety horizon.
    r = rule(Repeat.DAILY, anchor=date(2026, 1, 1))
    since = utc(2026, 1, 1, 6)
    moment = utc(2027, 5, 17, 12)
    assert latest_up_to(r, moment, since, MSK) == utc(2027, 5, 17, 6)


def test_fires_on() -> None:
    r = rule(Repeat.WEEKLY, weekdays=WEEKDAYS)
    assert fires_on(r, date(2026, 10, 2)) and not fires_on(r, date(2026, 10, 3))
    assert not fires_on(r, MON - timedelta(days=7))  # before the anchor


@pytest.mark.parametrize(
    "bad",
    [
        rule(Repeat.DAILY, "24:00"),
        rule(Repeat.DAILY, "9:00"),
        rule(Repeat.WEEKLY),
        rule(Repeat.WEEKLY, weekdays=0),
        rule(Repeat.WEEKLY, weekdays=128),
        rule(Repeat.WEEKLY, weekdays=1, interval_weeks=3),
        rule(Repeat.MONTHLY),
        rule(Repeat.MONTHLY, month_day=0),
        rule(Repeat.MONTHLY, month_day=32),
        rule(Repeat.NONE),
    ],
)
def test_invalid_rules(bad: Rule) -> None:
    with pytest.raises(InvalidInput) as error:
        bad.validate()
    assert error.value.params == {"field": "repeat", "reason": "repeat_invalid"}


@pytest.mark.parametrize(
    ("r", "ru", "en"),
    [
        (rule(Repeat.DAILY, "21:00"), "каждый день в 21:00", "every day at 21:00"),
        (rule(Repeat.WEEKLY, weekdays=WEEKDAYS), "по будням в 09:00", "on weekdays at 09:00"),
        (rule(Repeat.WEEKLY, weekdays=WEEKENDS), "по выходным в 09:00", "on weekends at 09:00"),
        (rule(Repeat.WEEKLY, "10:40", weekdays=2 | 8), "вт, чт в 10:40", "Tue, Thu at 10:40"),
        (
            rule(Repeat.WEEKLY, weekdays=4, interval_weeks=2),
            "раз в 2 недели: ср в 09:00",
            "every other week: Wed at 09:00",
        ),
        (
            rule(Repeat.MONTHLY, "12:00", month_day=5),
            "каждый месяц 5-го в 12:00",
            "monthly on day 5 at 12:00",
        ),
    ],
)
def test_describe(r: Rule, ru: str, en: str) -> None:
    assert describe(r, translator("ru")) == ru
    assert describe(r, translator("en")) == en


def test_weekday_short() -> None:
    assert [weekday_short(i, "ru") for i in range(7)] == ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    assert weekday_short(0, "en") == "Mon"
