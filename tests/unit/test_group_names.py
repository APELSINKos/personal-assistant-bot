from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from assistant.core.services.group_names import GroupHeader, name_key, read_header, search_keys

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
EMPTY_GROUP = (
    b"BEGIN:VCALENDAR\r\nPRODID:-//github.com/ical-org/ical.net//NONSGML ical.net//EN\r\n"
    b"VERSION:2.0\r\nX-WR-CALNAME:\xd0\x98\xd0\x92\xd0\x91\xd0\x9e-02-20\r\n"
    b"BEGIN:VTIMEZONE\r\nTZID:Europe/Moscow\r\nEND:VTIMEZONE\r\nEND:VCALENDAR\r\n"
)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("ИКБО-63-24", "икбо6324"),
        ("икбо 63 24", "икбо6324"),
        ("  ИКБО—63—24 ", "икбо6324"),
        ("KMБO-01-24", "кмбо0124"),  # Latin K, M, O among Cyrillic letters
        ("ЁЖ-1", "еж1"),
        ("", ""),
    ],
)
def test_name_key(text: str, key: str) -> None:
    assert name_key(text) == key


@pytest.mark.parametrize(
    ("query", "keys"),
    [
        ("ИКБО-63-24", ["икбо6324"]),
        ("ikbo-63-24", ["iкво6324", "икбо6324"]),  # lookalikes first, then transliteration
        ("IKBO 63", ["iкво63", "икбо63"]),
        ("KHBBO-05-25", ["кнвво0525", "хббо0525"]),
        ("63-24", ["6324"]),
        (" - ", []),
    ],
)
def test_search_keys(query: str, keys: list[str]) -> None:
    assert search_keys(query) == keys


def test_the_header_of_a_current_group() -> None:
    head = (FIXTURES / "mirea_ikbo_63_24.ics").read_bytes()[:4096]
    assert read_header(head) == GroupHeader("ИКБО-63-24", date(2026, 12, 31))


def test_an_old_group_without_a_timetable() -> None:
    assert read_header(EMPTY_GROUP) == GroupHeader("ИВБО-02-20", None)


@pytest.mark.parametrize(
    "head",
    [
        b"<!DOCTYPE html><html><head><title>404</title></head></html>",
        b"",
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n",  # no name
        b"BEGIN:VCALENDAR\r\nX-WR-CALNAME: -- \r\n",  # a name without letters or digits
    ],
)
def test_what_is_not_a_group(head: bytes) -> None:
    assert read_header(head) is None


def test_a_folded_name_line() -> None:
    head = b"BEGIN:VCALENDAR\r\nX-WR-CALNAME:\xd0\x98\xd0\x9a\xd0\x91\xd0\x9e-\r\n 63-24\r\n"
    assert read_header(head) == GroupHeader("ИКБО-63-24", None)
