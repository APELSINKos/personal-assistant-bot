"""An iCalendar file → the lessons and week labels of a date window.

A calendar comes from anyone, so the parser guards itself three ways. Events the expansion
cannot read or that repeat more than daily are dropped one by one, so a bad event costs only
itself, and more than `MAX_SERIES` recurring events are refused. The expansion reads only the
window and stops past `MAX_OCCURRENCES`. And `parse_isolated` runs it all in a child Python
process killed after `PARSE_SECONDS`: dateutil can spend minutes inside one call on a rule
that never matches, and nothing can stop a thread.

Callers use `parse_isolated` through `asyncio.to_thread`; `parse` is the same work in this
process (a semester of a MIREA group takes ~0.3 s). A calendar that cannot be read is
`InvalidInput(field="calendar", reason="not_calendar")`, one too big or too slow is
`InvalidInput(field="calendar", reason="too_large")`.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from assistant.core.errors import InvalidInput
from assistant.core.timeutil import UTC, local_to_utc

log = logging.getLogger(__name__)

# More occurrences than any timetable has in the window: the expansion stops there and the
# calendar is refused as "too_large". The count runs between the library's yields, so it
# cannot stop slow work inside one rule; the child's time limit does.
MAX_OCCURRENCES = 3000
# More recurring events than any timetable has: refused as "too_large" before expanding.
MAX_SERIES = 500
# A parse running longer is killed, and the calendar is refused as "too_large".
PARSE_SECONDS = 15.0
# Tests turn it off so the suite does not start a Python process per calendar.
ISOLATED = True
TITLE_LENGTH = 200
ROOM_LENGTH = 100
LABEL_LENGTH = 40
NAME_LENGTH = 100
UID_LENGTH = 255
_KIND_LENGTH = 8
# A lesson never repeats more often than daily; such rules only make the expansion explode.
_SUB_DAILY = frozenset({"SECONDLY", "MINUTELY", "HOURLY"})
# A timetable puts the time in DTSTART; these parts only multiply the occurrences of a day.
_TIME_PARTS = ("BYSECOND", "BYMINUTE", "BYHOUR")
# What the library reads from every event without a guard, with the type it needs.
_TYPED = (("DTEND", date), ("RECURRENCE-ID", date), ("DURATION", timedelta))
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


def _usable(event: Any) -> bool:
    """One start, end, rule, sequence and UID of the types the library expects, repeating at
    most daily. The library reads them unguarded: a bad one would sink the whole calendar."""
    if not isinstance(event["DTSTART"].dt, date):
        return False
    for key, kind in _TYPED:
        value = event.get(key)
        if value is not None and not isinstance(value.dt, kind):
            return False
    if not isinstance(event.get("SEQUENCE", 0), int) or not isinstance(event.get("UID", ""), str):
        return False
    rule = event.get("RRULE")
    if rule is None:
        return True
    # Several RRULE lines come as a list, an unreadable one as text.
    freq = rule.get("FREQ", []) if isinstance(rule, icalendar.vRecur) else []
    return (
        len(freq) == 1
        and str(freq[0]).upper() not in _SUB_DAILY
        and not any(part in rule for part in _TIME_PARTS)
    )


def _drop_unusable(component: Any) -> int:
    """Removes the events `_usable` refuses at any depth (the library walks them all) and
    returns how many recurring ones are left."""
    kept: list[Any] = []
    series = 0
    for sub in component.subcomponents:
        if sub.name == "VEVENT":
            try:
                usable = _usable(sub)
            except Exception:  # whatever one odd event raises costs only that event
                usable = False
            if not usable:
                continue
            if "RRULE" in sub:
                series += 1
        series += _drop_unusable(sub)
        kept.append(sub)
    component.subcomponents = kept
    return series


def _sanitize(calendar: Any) -> None:
    """Drops what the expansion cannot read or would explode on: an odd event or header costs
    only itself, not the calendar."""
    if _drop_unusable(calendar) > MAX_SERIES:
        raise InvalidInput(field="calendar", reason="too_large")
    zone = calendar.get("X-WR-TIMEZONE")
    if zone is not None:
        try:
            ZoneInfo(str(zone))  # what the library does with it
        except Exception:  # unknown ("GMT+3", Windows names), not a key, or a folder ("Europe")
            # Floating times are then read in the city zone, as without the header.
            del calendar["X-WR-TIMEZONE"]


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
        _sanitize(calendar)
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


def _iso(value: date) -> str:
    return value.isoformat()  # a datetime keeps its time and offset


def _from_json(output: bytes) -> Timetable | InvalidInput:
    """The child's answer: its timetable or its refusal. Anything else raises ValueError,
    KeyError or TypeError."""
    answer = json.loads(output)
    if "error" in answer:
        return InvalidInput(**answer["error"])
    table = answer["table"]
    return Timetable(
        name=table["name"],
        lessons=[
            ParsedLesson(
                uid=item["uid"],
                starts_at=datetime.fromisoformat(item["starts_at"]),
                ends_at=datetime.fromisoformat(item["ends_at"]),
                title=item["title"],
                kind=item["kind"],
                room=item["room"],
            )
            for item in table["lessons"]
        ],
        weeks=[
            ParsedWeek(
                date.fromisoformat(item["start"]), date.fromisoformat(item["end"]), item["label"]
            )
            for item in table["weeks"]
        ],
    )


def parse_isolated(
    body: bytes, start: datetime, end: datetime, tz: str, *, seconds: float = PARSE_SECONDS
) -> Timetable:
    """`parse` in a child Python process, killed after `seconds`; only JSON comes back.
    Blocking: call it through `asyncio.to_thread`."""
    if not ISOLATED:
        return parse(body, start, end, tz)
    try:
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "assistant.core.services.ical",
                start.isoformat(),
                end.isoformat(),
                tz,
            ],
            input=body,
            capture_output=True,
            timeout=seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:  # `run` has killed the child
        raise InvalidInput(field="calendar", reason="too_large") from None
    try:
        answer = _from_json(done.stdout) if done.returncode == 0 else None
    except (ValueError, KeyError, TypeError):
        answer = None
    if isinstance(answer, InvalidInput):
        raise answer
    if answer is None:
        lines = done.stderr.decode(errors="replace").strip().splitlines() or [""]
        log.warning("calendar parser failed with exit code %s: %s", done.returncode, lines[-1])
        raise _not_calendar()
    return answer


def _main() -> None:
    """The child of `parse_isolated`: the body on stdin, the window and the zone in argv, one
    JSON object on stdout."""
    start, end, tz = sys.argv[1:]
    body = sys.stdin.buffer.read()
    answer: dict[str, Any]
    try:
        table = parse(body, datetime.fromisoformat(start), datetime.fromisoformat(end), tz)
    except InvalidInput as error:
        answer = {"error": error.params}
    else:
        answer = {"table": asdict(table)}
    # json escapes everything non-ASCII, so the console encoding of the pipe does not matter.
    print(json.dumps(answer, default=_iso))


if __name__ == "__main__":
    _main()
