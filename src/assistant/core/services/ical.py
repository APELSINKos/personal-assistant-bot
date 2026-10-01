"""An iCalendar file → the lessons and week labels of a date window.

Pure and CPU-bound (a semester of a MIREA group takes ~0.3 s): call it through
`asyncio.to_thread`. Anything that is not a readable calendar becomes
`InvalidInput(field="calendar", reason="not_calendar")`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import icalendar
import recurring_ical_events

from assistant.core.errors import InvalidInput
from assistant.core.timeutil import UTC, local_to_utc

# More occurrences than any timetable has in the window: a bigger calendar is refused as
# "too_large" instead of being expanded for a minute (6000 daily series take ~60 s in full).
MAX_OCCURRENCES = 3000
TITLE_LENGTH = 200
ROOM_LENGTH = 100
LABEL_LENGTH = 40
NAME_LENGTH = 100
UID_LENGTH = 255
_KIND_LENGTH = 8
# A lesson never repeats more often than daily; such rules only make the expansion explode.
_SUB_DAILY = frozenset({"SECONDLY", "MINUTELY", "HOURLY"})
# «5 неделя», «5-я неделя», «Неделя 5», "Week 5", "5 week" — the all-day events that name weeks.
_WEEK = re.compile(
    r"^\s*(?:\d{1,2}\s*(?:-?я\s*)?(?:неделя|нед\.?|week)|(?:неделя|week)\s*\d{1,2})\s*$",
    re.IGNORECASE,
)
# The lesson type MIREA writes in front of the subject when CATEGORIES is missing: «ЛК …».
_KIND_PREFIX = re.compile(r"^([A-ZА-ЯЁ]{2,5})\s+\S")


@dataclass(frozen=True)
class ParsedLesson:
    uid: str
    starts_at: datetime  # aware UTC
    ends_at: datetime  # aware UTC
    title: str
    kind: str | None  # «ЛК», «ПР», … — only for MIREA calendars
    room: str | None


@dataclass(frozen=True)
class ParsedWeek:
    start: date
    end: date  # exclusive
    label: str


@dataclass(frozen=True)
class Timetable:
    name: str | None
    lessons: list[ParsedLesson]
    weeks: list[ParsedWeek]


def _not_calendar() -> InvalidInput:
    return InvalidInput(field="calendar", reason="not_calendar")


def looks_like_calendar(body: bytes) -> bool:
    return body.lstrip(b"\xef\xbb\xbf \t\r\n").upper().startswith(b"BEGIN:VCALENDAR")


def _text(component: Any, key: str) -> str:
    value = component.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return " ".join(str(value).split())


def _categories(component: Any) -> list[str]:
    value = component.get("CATEGORIES")
    if value is None:
        return []
    groups = value if isinstance(value, list) else [value]
    found: list[str] = []
    for group in groups:
        for category in getattr(group, "cats", [group]):
            text = " ".join(str(category).split())
            if text:
                found.append(text)
    return found


def _kind_and_title(summary: str, categories: list[str], mirea: bool) -> tuple[str | None, str]:
    if not mirea:
        return None, summary
    kind = next((c for c in categories if len(c) <= _KIND_LENGTH), None)
    if kind is None:
        match = _KIND_PREFIX.match(summary)
        kind = match.group(1) if match else None
    if kind and summary.startswith(kind + " "):
        summary = summary[len(kind) + 1 :].strip()
    return kind, summary or kind or ""


def _moment(value: datetime, tz: str) -> datetime:
    # A floating time (no zone, no X-WR-TIMEZONE) is read in the user's city zone.
    if value.tzinfo is None:
        return local_to_utc(value, tz)
    return value.astimezone(UTC)


def _end_of(event: Any, start: datetime | date) -> datetime | date:
    end = event.get("DTEND")
    if end is not None:
        return end.dt  # type: ignore[no-any-return]
    duration = event.get("DURATION")
    if duration is not None:
        return start + duration.dt  # type: ignore[no-any-return]
    return start


def _without_sub_daily(calendar: Any) -> None:
    calendar.subcomponents = [
        sub
        for sub in calendar.subcomponents
        if not (
            sub.name == "VEVENT"
            and sub.get("RRULE") is not None
            and any(str(freq).upper() in _SUB_DAILY for freq in sub["RRULE"].get("FREQ", []))
        )
    ]


def _occurrences(calendar: Any, start: datetime, end: datetime, tz: str) -> list[Any]:
    """The occurrences from `start` up to `end`, in time order, read lazily: expanding only
    what the window needs keeps a huge or endless calendar from eating the CPU."""
    found: list[Any] = []
    end_day = end.astimezone(UTC).date()
    for event in recurring_ical_events.of(calendar, skip_bad_series=True).after(start):
        raw_start = event.get("DTSTART")
        if raw_start is None:
            continue
        first = raw_start.dt
        if isinstance(first, datetime):
            if _moment(first, tz) >= end:
                break
        elif first > end_day:
            # Occurrences come in start order, but the library sorts a date against a time in
            # the time's own zone: the next day's all-day items can come before a lesson still
            # inside the window (its early morning in a zone east of UTC). A later date ends the
            # expansion — an endless all-day series would otherwise be read up to the year 9999.
            if first > end_day + timedelta(days=1):
                break
            continue
        if len(found) >= MAX_OCCURRENCES:
            raise InvalidInput(field="calendar", reason="too_large")
        found.append(event)
    return found


def parse(body: bytes, start: datetime, end: datetime, tz: str) -> Timetable:
    """Lessons starting in [start, end) and the week labels overlapping it."""
    if not looks_like_calendar(body):
        raise _not_calendar()
    try:
        calendar = icalendar.Calendar.from_ical(body)
        mirea = any(sub.name == "X-SCHEDULE-VERSION" for sub in calendar.subcomponents)
        _without_sub_daily(calendar)
        occurrences = _occurrences(calendar, start, end, tz)
    except InvalidInput:
        raise
    except Exception as error:  # the libraries raise many kinds of errors on broken input
        raise _not_calendar() from error

    lessons: dict[tuple[str, datetime], ParsedLesson] = {}
    weeks: dict[date, ParsedWeek] = {}
    for event in occurrences:
        if _text(event, "STATUS").upper() == "CANCELLED":
            continue
        first = event["DTSTART"].dt
        summary = _text(event, "SUMMARY")
        if not isinstance(first, datetime):  # an all-day event: a week label or nothing
            if _WEEK.match(summary):
                last = _end_of(event, first)
                if isinstance(last, datetime) or last <= first:
                    last = first + timedelta(days=1)
                weeks[first] = ParsedWeek(first, last, summary[:LABEL_LENGTH])
            continue
        kind, title = _kind_and_title(summary, _categories(event), mirea)
        if not title:
            continue
        starts_at = _moment(first, tz)
        last = _end_of(event, first)
        ends_at = _moment(last, tz) if isinstance(last, datetime) else starts_at
        uid = _text(event, "UID") or f"{summary}|{first.isoformat()}"
        lesson = ParsedLesson(
            uid=uid[:UID_LENGTH],
            starts_at=starts_at,
            ends_at=max(ends_at, starts_at),
            title=title[:TITLE_LENGTH],
            kind=kind,
            room=_text(event, "LOCATION")[:ROOM_LENGTH] or None,
        )
        lessons[(lesson.uid, lesson.starts_at)] = lesson
    name = _text(calendar, "X-WR-CALNAME")[:NAME_LENGTH] or None
    return Timetable(
        name=name,
        lessons=sorted(lessons.values(), key=lambda item: (item.starts_at, item.title)),
        weeks=sorted(weeks.values(), key=lambda item: item.start),
    )
