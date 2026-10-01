"""MIREA group names: the search key and what the first bytes of a group's calendar say."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from assistant.core.timeutil import SUPPORTED_YEARS, UTC, to_local

NAME_LENGTH = 40
MIREA_ZONE = "Europe/Moscow"
# Latin letters that look like Cyrillic ones («KMБO» pasted from somewhere mixed).
_TWINS = str.maketrans("abcehkmoptxy", "авсенкмортху")
# A group typed on an English keyboard: «ikbo-63-24». Longer sounds first.
_TRANSLIT = (
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"),
    ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("yo", "е"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"),
    ("i", "и"), ("j", "й"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"),
    ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"),
    ("c", "ц"), ("y", "ы"), ("w", "в"), ("x", "кс"), ("q", "к"),
)  # fmt: skip
_NOT_KEY = re.compile(r"[^0-9a-zа-я]")
# Content lines may be folded (CRLF + space); X-SV-END looks like 2026-12-30T21:00:00.0000000Z.
_FOLD = re.compile(rb"\r?\n[ \t]")
_CALNAME = re.compile(rb"^X-WR-CALNAME:(.+?)\r?$", re.MULTILINE)
_SV_END = re.compile(rb"^X-SV-END:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", re.MULTILINE)


@dataclass(frozen=True)
class GroupHeader:
    name: str
    # The last day of the semester in Moscow; date.max: open-ended (X-SV-END holds .NET's
    # DateTime.MaxValue, a timetable without an end); None: no X-SV-END at all (no timetable).
    semester_end: date | None


def name_key(text: str) -> str:
    """«ИКБО-63-24», «икбо 63 24» and lookalike-Latin spellings all become «икбо6324»."""
    lowered = text.lower().replace("ё", "е").translate(_TWINS)
    return _NOT_KEY.sub("", lowered)


def _transliterated(text: str) -> str:
    result = text.lower()
    for latin, cyrillic in _TRANSLIT:
        result = result.replace(latin, cyrillic)
    return result


def search_keys(query: str) -> list[str]:
    """Every key a query may mean: as typed (lookalikes mapped) and read as transliteration."""
    keys = [name_key(query)]
    if re.search(r"[a-zA-Z]", query):
        keys.append(name_key(_transliterated(query)))
    return [key for key in dict.fromkeys(keys) if key]


def read_header(head: bytes) -> GroupHeader | None:
    """The group's name and semester end from the beginning of its calendar, or None when
    the bytes are not a group calendar at all (an error page, a cut-off response) or its
    semester end is not a date."""
    text = _FOLD.sub(b"", head)
    if not text.lstrip(b"\xef\xbb\xbf \t\r\n").upper().startswith(b"BEGIN:VCALENDAR"):
        return None
    found = _CALNAME.search(text)
    if found is None:
        return None
    name = " ".join(found.group(1).decode("utf-8", "replace").split())[:NAME_LENGTH]
    if not name_key(name):
        return None
    end = _SV_END.search(text)
    semester_end = None
    if end is not None:
        try:
            moment = datetime.fromisoformat(end.group(1).decode()).replace(tzinfo=UTC)
        except ValueError:  # 0000-00-00, a 13th month: no end anyone can read
            return None
        if moment.year >= SUPPORTED_YEARS.stop:
            # An end past the supported years: .NET's DateTime.MaxValue (9999-12-31T23:59:59…)
            # for a timetable without one. Moved to Moscow it would not even fit in a date.
            semester_end = date.max
        else:
            semester_end = to_local(moment, MIREA_ZONE).date()
    return GroupHeader(name, semester_end)
