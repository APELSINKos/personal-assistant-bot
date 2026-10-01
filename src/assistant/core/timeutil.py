"""Time helpers. Everything stored is aware UTC; local time exists only at the edges."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "SUPPORTED_YEARS",
    "UTC",
    "digest_window_date",
    "is_valid_timezone",
    "local_to_utc",
    "local_today",
    "now_local",
    "parse_hhmm",
    "to_local",
    "utcnow",
]

_HHMM = re.compile(r"^\s*(\d{1,2}):(\d{1,2})\s*$")
# The calendar dates from the outside may use; checked before any date arithmetic, since a
# year far outside it can overflow it.
SUPPORTED_YEARS = range(2000, 2101)


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_local(moment: datetime, tz_name: str) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("expected an aware datetime")
    return moment.astimezone(ZoneInfo(tz_name))


def now_local(tz_name: str, now: datetime | None = None) -> datetime:
    return to_local(now or utcnow(), tz_name)


def local_today(tz_name: str, now: datetime | None = None) -> date:
    return now_local(tz_name, now).date()


def local_to_utc(wall: datetime, tz_name: str) -> datetime:
    """Interpret a naive wall-clock time in a zone.

    With fold=0 a time inside a DST gap resolves to the moment after the gap
    (02:30 → 03:30) and an ambiguous time resolves to its first occurrence.
    """
    if wall.tzinfo is not None:
        raise ValueError("expected a naive wall-clock datetime")
    return wall.replace(tzinfo=ZoneInfo(tz_name), fold=0).astimezone(UTC)


def digest_window_date(now_local: datetime, morning_time: str, minutes: int = 60) -> date | None:
    """Local date that owns the digest window containing `now_local`, or None.

    A window that starts at 23:30 and ends at 00:30 belongs to the day it started.
    """
    hours, mins = (int(part) for part in morning_time.split(":"))
    wall_now = now_local.replace(tzinfo=None)
    for day in (wall_now.date(), wall_now.date() - timedelta(days=1)):
        start = datetime.combine(day, time(hours, mins))
        if start <= wall_now < start + timedelta(minutes=minutes):
            return day
    return None


def parse_hhmm(text: str) -> str | None:
    match = _HHMM.match(text)
    if not match:
        return None
    hours, mins = int(match.group(1)), int(match.group(2))
    if hours > 23 or mins > 59:
        return None
    return f"{hours:02d}:{mins:02d}"


def is_valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    # A folder of the database («Europe») is opened like a zone file and fails with an OSError
    # (IsADirectoryError, PermissionError on Windows) rather than ZoneInfoNotFoundError.
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True
