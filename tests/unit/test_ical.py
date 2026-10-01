from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from assistant.core.errors import InvalidInput
from assistant.core.services import ical
from assistant.core.services.ical import ParsedLesson, ParsedWeek

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
# Monday 28 September 00:00 → Monday 12 October 00:00 in Moscow: two weeks, both parities.
START = datetime(2026, 9, 27, 21, tzinfo=UTC)
END = datetime(2026, 10, 11, 21, tzinfo=UTC)


def utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_a_mirea_group_calendar() -> None:
    table = ical.parse(read("mirea_ikbo_63_24.ics"), START, END, "Europe/Moscow")
    assert table.name == "ИКБО-63-24"
    assert [(item.starts_at, item.kind, item.title, item.room) for item in table.lessons] == [
        (utc(2026, 9, 30, 9, 40), "ПР", "Разработка баз данных", "И-212-б (В-78)"),
        (utc(2026, 10, 1, 6), "ДОП", "Военная кафедра", "ВУЦ (У-7/1)"),
        (
            utc(2026, 10, 2, 6),
            "ЛК",
            "Проектирование и разработка мобильных приложений на языке Котлин",
            "А-18 (В-78)",
        ),
        (utc(2026, 10, 7, 9, 40), "ПР", "Разработка баз данных", "И-212-б (В-78)"),
        (
            utc(2026, 10, 9, 6),
            "ЛК",
            "Проектирование и разработка мобильных приложений на языке Котлин",
            "А-18 (В-78)",
        ),
        (utc(2026, 10, 10, 6), "ЛК", "Разработка баз данных", "А-15 (В-78)"),
    ]
    first = table.lessons[0]
    assert first.ends_at == utc(2026, 9, 30, 11, 10)
    assert first.uid == "75bb3b9e-e6c9-58d8-8e4d-a76fac78eade"
    assert table.weeks == [
        ParsedWeek(date(2026, 9, 21), date(2026, 9, 28), "4 неделя"),
        ParsedWeek(date(2026, 9, 28), date(2026, 10, 5), "5 неделя"),
        ParsedWeek(date(2026, 10, 5), date(2026, 10, 12), "6 неделя"),
    ]


def test_a_calendar_of_another_university() -> None:
    table = ical.parse(read("foreign.ics"), START, END, "Europe/Moscow")
    assert table.name == "Physics 101"
    assert table.lessons == [
        # Floating times are read in X-WR-TIMEZONE (Berlin, UTC+2 in summer time).
        ParsedLesson(
            "lecture@example.edu",
            utc(2026, 9, 29, 8),
            utc(2026, 9, 29, 9, 30),
            "Physics lecture",
            None,
            "Room 5",
        ),
        # No end and no duration: the lesson ends when it starts.
        ParsedLesson(
            "seminar@example.edu", utc(2026, 10, 1, 8), utc(2026, 10, 1, 8), "Seminar", None, None
        ),
        # One occurrence moved by a RECURRENCE-ID override.
        ParsedLesson(
            "lecture@example.edu",
            utc(2026, 10, 6, 10),
            utc(2026, 10, 6, 11, 30),
            "Physics lecture (moved)",
            None,
            "Room 7",
        ),
    ]
    # The cancelled seminar, the public holiday and the every-minute rule are not lessons.
    assert table.weeks == [ParsedWeek(date(2026, 9, 28), date(2026, 10, 5), "Week 5")]


def test_a_windows_time_zone_from_outlook() -> None:
    table = ical.parse(read("outlook.ics"), START, END, "Asia/Tokyo")
    assert [(item.starts_at, item.title, item.room) for item in table.lessons] == [
        (utc(2026, 9, 29, 6), "Английский язык", "ауд. 204")
    ]


def test_floating_times_without_a_zone_use_the_city_zone() -> None:
    body = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:a\r\n"
        b"DTSTART:20261001T090000\r\nDTEND:20261001T100000\r\nSUMMARY:Math\r\n"
        b"END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    table = ical.parse(body, START, END, "Asia/Yekaterinburg")
    assert [(item.starts_at, item.ends_at) for item in table.lessons] == [
        (utc(2026, 10, 1, 4), utc(2026, 10, 1, 5))
    ]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not a calendar at all",
        b"<!DOCTYPE html><html><body>Login</body></html>",
        b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n",  # cut off in the middle
    ],
)
def test_what_is_not_a_calendar(body: bytes) -> None:
    with pytest.raises(InvalidInput) as caught:
        ical.parse(body, START, END, "Europe/Moscow")
    assert caught.value.params == {"field": "calendar", "reason": "not_calendar"}


def test_an_empty_calendar_is_fine_and_has_nothing() -> None:
    body = b"\xef\xbb\xbfBEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    assert ical.parse(body, START, END, "Europe/Moscow") == ical.Timetable(None, [], [])


def test_a_broken_event_is_skipped_not_fatal() -> None:
    body = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        b"BEGIN:VEVENT\r\nUID:bad\r\nDTSTART:garbage\r\nSUMMARY:x\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:good\r\nDTSTART:20261001T090000Z\r\nSUMMARY:Good\r\nEND:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )
    table = ical.parse(body, START, END, "Europe/Moscow")
    assert [item.title for item in table.lessons] == ["Good"]


def _daily_series(count: int) -> bytes:
    events = "".join(
        f"BEGIN:VEVENT\r\nUID:e{i}\r\n"
        f"DTSTART;TZID=Europe/Moscow:20260901T{8 + i % 12:02d}{i % 60:02d}00\r\n"
        f"RRULE:FREQ=DAILY\r\nSUMMARY:ParsedLesson {i}\r\nEND:VEVENT\r\n"
        for i in range(count)
    )
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{events}END:VCALENDAR\r\n".encode()


def test_a_huge_calendar_is_refused_quickly() -> None:
    # 400 daily series × 120 days would be 48 000 lessons; the expansion stops at the limit.
    with pytest.raises(InvalidInput) as caught:
        ical.parse(_daily_series(400), START, utc(2027, 1, 26), "Europe/Moscow")
    assert caught.value.params == {"field": "calendar", "reason": "too_large"}


@pytest.mark.parametrize(
    ("freq", "days"),
    [
        ("YEARLY", [date(2026, 9, 29)]),
        ("MONTHLY", [date(2026, 9, 29)]),
        ("WEEKLY", [date(2026, 9, 28), date(2026, 10, 5)]),
        ("DAILY", [date(2026, 9, 27) + timedelta(days=n) for n in range(15)]),
    ],
)
def test_an_endless_all_day_series_stops_after_the_window(freq: str, days: list[date]) -> None:
    # The lessons end inside the window, so no lesson after it can stop the expansion.
    body = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:math\r\nDTSTART;TZID=Europe/Moscow:20260901T090000\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=6\r\nSUMMARY:Math\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:week\r\nDTSTART;VALUE=DATE:20250929\r\n"
        f"RRULE:FREQ={freq}\r\nSUMMARY:Week 1\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    began = time.perf_counter()
    table = ical.parse(body, START, END, "Europe/Moscow")
    assert time.perf_counter() - began < 2
    assert [item.starts_at for item in table.lessons] == [utc(2026, 9, 29, 6), utc(2026, 10, 6, 6)]
    assert table.weeks == [ParsedWeek(day, day + timedelta(days=1), "Week 1") for day in days]


def test_an_all_day_item_after_the_window_does_not_hide_a_late_lesson() -> None:
    # The library sorts a date against a time in the time's own zone, so the item of 12 October
    # comes before a Tokyo lesson at 05:00 on the 12th — 20:00 UTC, still inside the window.
    body = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        b"BEGIN:VEVENT\r\nUID:early\r\nDTSTART;TZID=Asia/Tokyo:20261012T050000\r\n"
        b"SUMMARY:Early lesson\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:week\r\nDTSTART;VALUE=DATE:20261012\r\nSUMMARY:Week 7\r\n"
        b"END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    table = ical.parse(body, START, END, "Europe/Moscow")
    assert [(item.starts_at, item.title) for item in table.lessons] == [
        (utc(2026, 10, 11, 20), "Early lesson")
    ]
    assert table.weeks == []


def test_long_texts_are_cut() -> None:
    title, room = "Т" * 300, "К" * 150
    body = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:long\r\n"
        f"DTSTART:20261001T090000Z\r\nSUMMARY:{title}\r\nLOCATION:{room}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()
    (item,) = ical.parse(body, START, END, "Europe/Moscow").lessons
    assert len(item.title) == ical.TITLE_LENGTH and len(item.room or "") == ical.ROOM_LENGTH


def test_a_kind_from_the_summary_when_categories_are_missing() -> None:
    lecture = "CATEGORIES:ЛК".encode()
    body, removed = re.subn(re.escape(lecture) + rb"\r?\n", b"", read("mirea_ikbo_63_24.ics"))
    assert removed == 3  # the fixture's three lecture series
    table = ical.parse(body, START, END, "Europe/Moscow")
    lectures = [item for item in table.lessons if item.title.startswith("Разработка баз")]
    assert [(item.kind, item.title) for item in lectures][-1] == ("ЛК", "Разработка баз данных")
