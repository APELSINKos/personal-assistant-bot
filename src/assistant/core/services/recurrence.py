"""Repeat rules of reminders: which local days a rule fires on and at which moments.

Everything is computed on the user's local calendar and only then turned into UTC, so a
reminder "every day at 21:00" stays at 21:00 across DST changes and after a move to another
city. The rules are small enough that walking the calendar day by day is simpler and easier
to trust than a general recurrence library.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from assistant.core.errors import InvalidInput
from assistant.core.i18n import Translator, weekday_short
from assistant.core.models import Repeat
from assistant.core.timeutil import local_to_utc, parse_hhmm, to_local

# Weekday bits: Monday = 1, Tuesday = 2, … Sunday = 64 (1 << date.weekday()).
ALL_DAYS = 0b1111111
WEEKDAYS = 0b0011111
WEEKENDS = 0b1100000
# The longest gap between two firings of a valid rule is under two months (monthly on the
# 31st still fires every month on its last day); a year is a generous safety bound.
_HORIZON = timedelta(days=400)


@dataclass(frozen=True)
class Rule:
    repeat: Repeat
    time_local: str
    anchor_date: date
    weekdays: int | None = None
    interval_weeks: int = 1
    month_day: int | None = None

    def validate(self) -> None:
        def invalid() -> InvalidInput:
            return InvalidInput(field="repeat", reason="repeat_invalid")

        if parse_hhmm(self.time_local) != self.time_local:
            raise invalid()
        if self.repeat is Repeat.WEEKLY:
            if self.weekdays is None or not 1 <= self.weekdays <= ALL_DAYS:
                raise invalid()
            if self.interval_weeks not in (1, 2):
                raise invalid()
        elif self.repeat is Repeat.MONTHLY:
            if self.month_day is None or not 1 <= self.month_day <= 31:
                raise invalid()
        elif self.repeat is not Repeat.DAILY:
            raise invalid()

    @property
    def clock(self) -> time:
        hours, minutes = (int(part) for part in self.time_local.split(":"))
        return time(hours, minutes)


def weekday_bit(day: date) -> int:
    return 1 << day.weekday()


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def fires_on(rule: Rule, day: date) -> bool:
    if day < rule.anchor_date:
        return False
    if rule.repeat is Repeat.DAILY:
        return True
    if rule.repeat is Repeat.WEEKLY:
        if rule.weekdays is None or not rule.weekdays & weekday_bit(day):
            return False
        weeks = (_monday(day) - _monday(rule.anchor_date)).days // 7
        return weeks % rule.interval_weeks == 0
    if rule.repeat is Repeat.MONTHLY and rule.month_day is not None:
        last = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(rule.month_day, last)
    return False


def local_days(rule: Rule, start: date, end: date | None = None) -> Iterator[date]:
    """Local dates the rule fires on, from `start` (or the anchor, if later) onwards.

    Walks up to `end` when given. Otherwise walks up to `start + _HORIZON`, a bound that
    exists only to protect `next_after` from a rule that (in theory) never fires again.
    """
    day = max(start, rule.anchor_date)
    last = end if end is not None else day + _HORIZON
    while day <= last:
        if fires_on(rule, day):
            yield day
        day += timedelta(days=1)


def moment_on(rule: Rule, day: date, tz: str) -> datetime:
    return local_to_utc(datetime.combine(day, rule.clock), tz)


def next_after(rule: Rule, after: datetime, tz: str) -> datetime:
    """The first firing strictly after `after` (aware), as aware UTC."""
    # Start a day early: in zones west of UTC the local date of `after` can be "behind".
    for day in local_days(rule, to_local(after, tz).date() - timedelta(days=1)):
        moment = moment_on(rule, day, tz)
        if moment > after:
            return moment
    raise InvalidInput(field="repeat", reason="repeat_invalid")


def between(
    rule: Rule, start: datetime, end: datetime, tz: str, limit: int = 500
) -> list[datetime]:
    """Firings in [start, end), at most `limit` of them.

    Walks the whole window regardless of its length; only `limit` can shorten the result.
    """
    found: list[datetime] = []
    last_day = to_local(end, tz).date()
    for day in local_days(rule, to_local(start, tz).date() - timedelta(days=1), last_day):
        if len(found) >= limit:
            break
        moment = moment_on(rule, day, tz)
        if start <= moment < end:
            found.append(moment)
    return found


def latest_up_to(rule: Rule, moment: datetime, since: datetime, tz: str) -> datetime:
    """The last firing in [since, moment]; `since` itself if there is none after it.

    Used when the bot was down: of several missed firings only the latest is delivered.
    """
    latest = since
    for found in between(rule, since, moment + timedelta(microseconds=1), tz, limit=10_000):
        latest = found
    return latest


def describe(rule: Rule, t: Translator) -> str:
    """«по будням в 09:00», «вт, чт в 10:40», «каждый месяц 5-го в 12:00»."""
    if rule.repeat is Repeat.DAILY:
        return t("repeat-daily", time=rule.time_local)
    if rule.repeat is Repeat.MONTHLY:
        return t("repeat-monthly", day=rule.month_day or 1, time=rule.time_local)
    bits = rule.weekdays or 0
    if rule.interval_weeks == 1 and bits == WEEKDAYS:
        return t("repeat-weekdays", time=rule.time_local)
    if rule.interval_weeks == 1 and bits == WEEKENDS:
        return t("repeat-weekends", time=rule.time_local)
    days = ", ".join(weekday_short(index, t.lang) for index in range(7) if bits & (1 << index))
    key = "repeat-biweekly" if rule.interval_weeks == 2 else "repeat-weekly"
    return t(key, days=days, time=rule.time_local)
