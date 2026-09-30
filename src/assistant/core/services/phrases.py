"""Understanding a reminder written as a phrase: «завтра в 9 купить молоко», «every monday at 10».

A message counts as a reminder only when it carries a time anchor — a clock time after a
preposition, «через …» / «in …», a day, a date or a repeat — so «купить 2 батона» stays plain
text. Recognised pieces are cut out of the message; what is left is the reminder's text.
Russian and English are both tried, whatever the interface language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from assistant.core.models import Repeat
from assistant.core.services.recurrence import (
    ALL_DAYS,
    WEEKDAYS,
    WEEKENDS,
    Rule,
    first_matching_day,
)

_RU_WEEKDAYS_ACC = (
    "понедельник",
    "вторник",
    "среду",
    "четверг",
    "пятницу",
    "субботу",
    "воскресенье",
)
_RU_WEEKDAYS_DAT = (
    "понедельникам",
    "вторникам",
    "средам",
    "четвергам",
    "пятницам",
    "субботам",
    "воскресеньям",
)
_RU_ORD_ACC = ("второй", "вторую", "второе")
_EN_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_RU_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_EN_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_NUMBERS = {
    "один": 1,
    "одну": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "пятнадцать": 15,
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
}

_W = r"(?<![\w])"  # start of a word (works for Cyrillic, unlike \b in some edge cases)
_E = r"(?![\w])"  # end of a word


def _alt(words: tuple[str, ...]) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


_RU_ACC = _alt(_RU_WEEKDAYS_ACC)
_RU_DAT = _alt(_RU_WEEKDAYS_DAT)
_EN_DAYS = _alt(tuple(d + "s" for d in _EN_WEEKDAYS))
_EN_DAY = _EN_DAYS + "|" + _alt(_EN_WEEKDAYS)
_EN_MON = _alt(_EN_MONTHS) + "|" + _alt(tuple(m[:3] for m in _EN_MONTHS))
_NUM = r"\d{1,3}|" + _alt(tuple(_NUMBERS))

PREFIX = re.compile(
    r"^\s*(?:(?:please|пожалуйста)" + _E + r"[\s,]*)?"
    r"(?:напомни(?:ть)?(?:\s+мне)?|remind\s+me(?:\s+to)?)" + _E + r"[\s,:—-]*"
)
POLITE = re.compile(r"^(?:please|пожалуйста)" + _E + r"[\s,]*", re.IGNORECASE)

REPEATS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(_W + r"(?:каждый\s+день|ежедневно|every\s*day|daily)" + _E), "daily"),
    (
        re.compile(
            _W + r"(?:по\s+будням|в\s+будни|по\s+рабочим\s+дням|каждый\s+будний\s+день"
            r"|(?:on\s+)?weekdays|every\s+weekday)" + _E
        ),
        "weekdays",
    ),
    (
        re.compile(_W + r"(?:по\s+выходным|в\s+выходные|(?:on\s+)?weekends|every\s+weekend)" + _E),
        "weekends",
    ),
    (
        re.compile(
            _W
            + r"(?:раз\s+в\s+(?:две|2)\s+недели)(?:\s+(?:по\s+(?P<dat>(?:"
            + _RU_DAT
            + r")(?:\s*(?:,|и)\s*(?:"
            + _RU_DAT
            + r"))*)|во?\s+(?P<acc>"
            + _RU_ACC
            + r")))?"
            + _E
        ),
        "biweekly",
    ),
    (
        re.compile(
            _W
            + r"(?:кажд(?:ый|ую|ое)\s+(?:"
            + _alt(_RU_ORD_ACC)
            + r")\s+)(?P<acc>(?:"
            + _RU_ACC
            + r")(?:\s*(?:,|и)\s*(?:"
            + _RU_ACC
            + r"))*)"
            + _E
        ),
        "biweekly",
    ),
    (
        re.compile(
            _W
            + r"every\s+other\s+(?P<en>(?:"
            + _EN_DAY
            + r")(?:\s*(?:,|and)\s*(?:"
            + _EN_DAY
            + r"))*)"
            + _E
        ),
        "biweekly",
    ),
    (
        re.compile(
            _W
            + r"кажд(?:ый|ую|ое)\s+(?P<acc>(?:"
            + _RU_ACC
            + r")(?:\s*(?:,|и)\s*(?:"
            + _RU_ACC
            + r"))*)"
            + _E
        ),
        "weekly",
    ),
    (
        re.compile(
            _W
            + r"по\s+(?P<dat>(?:"
            + _RU_DAT
            + r")(?:\s*(?:,|и)\s*(?:по\s+)?(?:"
            + _RU_DAT
            + r"))*)"
            + _E
        ),
        "weekly",
    ),
    (
        re.compile(
            _W
            + r"every\s+(?P<en>(?:"
            + _EN_DAY
            + r")(?:\s*(?:,|and)\s*(?:"
            + _EN_DAY
            + r"))*)"
            + _E
        ),
        "weekly",
    ),
    (
        re.compile(
            _W + r"on\s+(?P<en>(?:" + _EN_DAYS + r")(?:\s*(?:,|and)\s*(?:" + _EN_DAYS + r"))*)" + _E
        ),
        "weekly",
    ),
    (
        re.compile(
            _W + r"(?:(?:каждый\s+месяц|ежемесячно)\s+(?P<md>\d{1,2})(?:-?го)?(?:\s+числа)?"
            r"|каждое\s+(?P<md2>\d{1,2})(?:-?е)?\s+число"
            r"|(?P<md3>\d{1,2})(?:-?го)?\s+числа\s+каждого\s+месяца"
            r"|(?:monthly|every\s+month)\s+on\s+the\s+(?P<md4>\d{1,2})(?:st|nd|rd|th)?"
            r"|on\s+the\s+(?P<md5>\d{1,2})(?:st|nd|rd|th)?\s+of\s+every\s+month)" + _E
        ),
        "monthly",
    ),
]

RELATIVE = re.compile(
    _W + r"(?:через|in)\s+(?:(?P<half>полчаса|half\s+an\s+hour)|(?P<oneandhalf>полтора\s+часа)"
    # hours and minutes: «через 1 час 30 минут», "in 2 hours and 15 minutes"
    r"|(?:(?P<hn>" + _NUM + r")\s+)?(?:час(?:а|ов)?|hours?|hrs?)\s+(?:(?:и|and)\s+)?"
    r"(?P<mn>" + _NUM + r")\s+(?:минут[уы]?|мин|minutes?|mins?)"
    r"|(?:(?P<n>" + _NUM + r")\s+)?(?P<unit>минут[уы]?|мин|час(?:а|ов)?|день|дня|дней|недел[юиь]"
    r"|minutes?|mins?|hours?|hrs?|days?|weeks?))" + _E
)
# With a year the date may follow «в / на» («в 10.12.2026»); without one «в 10.12» is a time.
DATE_NUMERIC_YEAR = re.compile(
    _W + r"(?:(?:в|во|на)\s+)?(?<![\d.:])(?P<d>\d{1,2})\.(?P<m>\d{2})\.(?P<y>\d{4}|\d{2})(?![\d.:])"
)
DATE_NUMERIC = re.compile(
    r"(?<!в\s)(?<!во\s)(?<!к\s)(?<![\d.:])(?P<d>\d{1,2})\.(?P<m>\d{2})(?![\d.:])"
)
DATE_RU = re.compile(
    _W + r"(?P<d>\d{1,2})\s+(?P<mon>" + _alt(_RU_MONTHS) + r")(?:\s+(?P<y>\d{4})(?:\s+года)?)?" + _E
)
DATE_EN = re.compile(
    _W + r"(?:on\s+)?(?:(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>" + _EN_MON + r")"
    r"|(?P<mon2>" + _EN_MON + r")\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?)(?:,?\s+(?P<y>\d{4}))?" + _E
)
DAY_WORD = re.compile(
    _W + r"(?:на\s+)?(?P<w>послезавтра|завтра|сегодня"
    r"|(?:the\s+)?day\s+after\s+tomorrow|tomorrow|today)" + _E
)
# «в следующую пятницу» / "next friday" is that day of the next Monday-based week.
WEEKDAY_ONCE = re.compile(
    _W + r"(?:(?:в|во|на)\s+(?:(?P<ru_next>следующ(?:ий|ую|ее))\s+|эт(?:от|у|о)\s+)?"
    r"(?P<ru>" + _RU_ACC + r")"
    r"|(?:on\s+)?(?:(?P<en_next>next)\s+|this\s+)?(?P<en>" + _alt(_EN_WEEKDAYS) + r"))" + _E
)
# After the number of «в N» / "at N": a hyphen suffix («9-м»), a decimal part («2.5») or a unit
# («в 2 раза», "at 5 stars") means a quantity, not a clock time. Units are whole words with
# explicit endings, so «в 7 метро» or «в 10 рубить дрова» stay times.
_UNITS = (
    r"раза?",
    "км",
    "кг",
    "м",
    "г",
    "л",
    "мл",
    "см",
    "мм",
    r"метр(?:а|е|у|ом|ов|ах|ами)?",
    r"километр(?:а|е|у|ом|ов|ах|ами)?",
    r"класс(?:а|е|у|ом|ы|ов|ах|ами)?",
    "лет",
    r"год(?:а|у|ом|ы|ов|ах)?",
    r"этаж(?:а|е|у|ом|и|ей|ах)?",
    r"процент(?:а|ы|ом|ов|ах)?",
    "минутах",
    "часах",
    "шагах",
    r"руб(?:\.|ль|ля|лю|лем|лей|лях|лями)?",
    "times",
    "percent",
    r"stars?",
    "km",
    "kg",
    r"miles?",
    r"years?",
    "floor",
)
_NOT_TIME = r"(?!-[^\W\d_]|[.,:]\d|\s*%|\s*(?:" + "|".join(_UNITS) + r")" + _E + r")"
TIME_WORD = re.compile(_W + r"(?:в|at)\s+(?P<w>полдень|полночь|noon|midnight)" + _E)
# «утром в 7» / «в 8 вечером» read like «в 7 утра» / «в 8 вечера» (the text has ё → е).
_PART_OF_DAY = {"утром": "утра", "днем": "дня", "вечером": "вечера", "ночью": "ночи"}
TIME_RU = re.compile(
    _W + r"(?:(?P<pre>" + _alt(tuple(_PART_OF_DAY)) + r")\s+)?"
    r"(?:в|во|к)\s+(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?"
    + _NOT_TIME
    + r"(?:\s*(?:ч|час(?:а|ов)?)"
    + _E
    + r")?"
    r"(?:\s+(?P<mer>" + _alt(("утра", "дня", "вечера", "ночи", *_PART_OF_DAY)) + r"))?" + _E
)
_MERIDIEM = r"[ap]\.?m\.?"  # am, a.m., pm, p.m.
TIME_EN = re.compile(
    _W
    + r"(?:at\s+(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?"
    + _NOT_TIME
    + r"\s*(?P<mer>"
    + _MERIDIEM
    + r")?"
    r"|(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<mer2>" + _MERIDIEM + r"))" + _E
)
TIME_BARE = re.compile(r"(?<![\w:.])(?P<h>\d{1,2}):(?P<m>\d{2})(?![\w:])")
LEADING_JUNK = re.compile(r"^(?:что(?:бы)?|о\s+том,?\s+что(?:бы)?|to|that)" + _E + r"\s*")


@dataclass(frozen=True)
class Parsed:
    """What a phrase says. Exactly one of the scheduling forms applies."""

    text: str
    time: str | None = None  # "HH:MM"
    day: date | None = None  # an explicit day (word or date)
    day_has_year: bool = True  # False for «25.09»: a past date then means next year
    weekday: int | None = None  # one-off «в пятницу»: 0 = Monday
    delta: timedelta | None = None  # «через 20 минут»: an exact moment
    delta_days: int | None = None  # «через 3 дня»: a day, the time comes separately
    repeat: Repeat = Repeat.NONE
    weekdays: int | None = None
    interval_weeks: int = 1
    month_day: int | None = None

    @property
    def needs_time(self) -> bool:
        return self.time is None and (self.delta is None or self.repeat is not Repeat.NONE)

    def with_time(self, hhmm: str) -> Parsed:
        return replace(self, time=hhmm)

    def when(self, now: datetime) -> datetime | None:
        """The local wall time of a one-off reminder (naive), or None if it is not one."""
        if self.repeat is not Repeat.NONE:
            return None
        wall = now.replace(tzinfo=None)
        if self.delta is not None:
            return (wall + self.delta).replace(second=0, microsecond=0)
        if self.time is None:
            return None
        clock = _clock(self.time)
        if self.delta_days is not None:
            return datetime.combine(wall.date() + timedelta(days=self.delta_days), clock)
        if self.day is not None:
            day = self.day
            if not self.day_has_year and day < wall.date():
                day = _yearly(day.month, day.day, wall.date()) or day
            return datetime.combine(day, clock)
        if self.weekday is not None:
            ahead = (self.weekday - wall.weekday()) % 7
            moment = datetime.combine(wall.date() + timedelta(days=ahead), clock)
            return moment if moment > wall else moment + timedelta(days=7)
        moment = datetime.combine(wall.date(), clock)
        return moment if moment > wall else moment + timedelta(days=1)

    def rule(self, now: datetime) -> Rule | None:
        """The repeat rule, anchored so that the first firing is the next one from `now`."""
        if self.repeat is Repeat.NONE or self.time is None:
            return None
        wall = now.replace(tzinfo=None)
        rule = Rule(
            repeat=self.repeat,
            time_local=self.time,
            anchor_date=wall.date(),
            weekdays=self.weekdays,
            interval_weeks=self.interval_weeks,
            month_day=self.month_day,
        )
        if self.interval_weeks == 2:
            # Every other week counts from the first firing: find it with a weekly rule.
            first = first_matching_day(rule, wall.date(), wall)
            if first is None:
                return None
            rule = replace(rule, anchor_date=first)
        return rule


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _yearly(month: int, day: int, since: date) -> date | None:
    """The first such date on or after `since` (Feb 29 waits for a leap year); None if none."""
    for year in range(since.year, since.year + 9):
        found = _date(year, month, day)
        if found is not None and found >= since:
            return found
    return None


def _clock(hhmm: str) -> time:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return time(hours, minutes)


def _hhmm(hours: int, minutes: int) -> str | None:
    if 0 <= hours <= 23 and 0 <= minutes <= 59:
        return f"{hours:02d}:{minutes:02d}"
    return None


def _with_meridiem(hours: int, meridiem: str | None) -> int:
    if meridiem in ("вечера", "дня", "pm"):
        return (
            hours + 12
            if 1 <= hours <= 11
            else (0 if hours == 12 and meridiem == "вечера" else hours)
        )
    if meridiem in ("утра", "am"):
        return 0 if hours == 12 else hours
    if meridiem == "ночи":
        return 0 if hours == 12 else (hours + 12 if 6 <= hours <= 11 else hours)
    return hours


def _number(word: str | None) -> int:
    if word is None:
        return 1
    return int(word) if word.isdigit() else _NUMBERS[word]


def _day_bits(words: str) -> int:
    bits = 0
    for index in range(7):
        for name in (_RU_WEEKDAYS_ACC[index], _RU_WEEKDAYS_DAT[index], _EN_WEEKDAYS[index]):
            if re.search(_W + name + r"s?" + _E, words):
                bits |= 1 << index
    return bits


class _Text:
    """The message with recognised pieces blanked out, keeping every other offset."""

    def __init__(self, original: str) -> None:
        low = original.lower()
        self.original = original if len(low) == len(original) else low
        self.low = low.replace("ё", "е")
        self.mask = list(self.low)

    @property
    def current(self) -> str:
        return "".join(self.mask)

    def take(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
        match = pattern.search(self.current)
        if match is not None:
            for index in range(match.start(), match.end()):
                self.mask[index] = "\0"
        return match

    def rest(self) -> str:
        kept = "".join(
            " " if blank == "\0" else char
            for char, blank in zip(self.original, self.mask, strict=True)
        )
        text = " ".join(kept.split())
        text = text.strip(" ,.;:—-–")
        text = POLITE.sub("", text)
        text = LEADING_JUNK.sub("", text)
        return text.strip(" ,.;:—-–")


def parse(message: str, now: datetime) -> Parsed | None:
    """None when the message has no time anchor at all — it is not a reminder."""
    work = _Text(" ".join(message.split()))
    prefix = PREFIX.match(work.low)
    if prefix is not None:
        for index in range(prefix.start(), prefix.end()):
            work.mask[index] = "\0"
    found: dict[str, Any] = {}

    for pattern, kind in REPEATS:
        match = work.take(pattern)
        if match is None:
            continue
        groups = match.groupdict()
        if kind == "daily":
            found["repeat"] = Repeat.DAILY
        elif kind in ("weekdays", "weekends"):
            found.update(
                repeat=Repeat.WEEKLY, weekdays=WEEKDAYS if kind == "weekdays" else WEEKENDS
            )
        elif kind == "monthly":
            day = next(int(v) for k, v in groups.items() if k.startswith("md") and v)
            if not 1 <= day <= 31:
                return None
            found.update(repeat=Repeat.MONTHLY, month_day=day)
        else:
            words = " ".join(v for k, v in groups.items() if k in ("acc", "dat", "en") and v)
            bits = _day_bits(words) if words else 1 << now.weekday()
            found.update(repeat=Repeat.WEEKLY, weekdays=bits & ALL_DAYS)
            if kind == "biweekly":
                found["interval_weeks"] = 2
        break

    # A repeat has no single moment: «через …» stays in its text.
    if "repeat" not in found and (match := work.take(RELATIVE)) is not None:
        unit = match.group("unit") or ""
        if match.group("half"):
            found["delta"] = timedelta(minutes=30)
        elif match.group("oneandhalf"):
            found["delta"] = timedelta(minutes=90)
        elif match.group("mn"):
            hours, minutes = _number(match.group("hn")), _number(match.group("mn"))
            found["delta"] = timedelta(hours=hours, minutes=minutes)
        elif unit.startswith(("мин", "min")):
            found["delta"] = timedelta(minutes=_number(match.group("n")))
        elif unit.startswith(("час", "hour", "hr")):
            found["delta"] = timedelta(hours=_number(match.group("n")))
        elif unit.startswith(("д", "day")):
            found["delta_days"] = _number(match.group("n"))
        else:
            found["delta_days"] = 7 * _number(match.group("n"))

    for pattern in (DATE_RU, DATE_EN, DATE_NUMERIC_YEAR, DATE_NUMERIC):
        match = pattern.search(work.current)
        if match is None:
            continue
        groups = match.groupdict()
        day_number = int(groups.get("d") or groups.get("d2") or 0)
        month_word = groups.get("mon") or groups.get("mon2")
        if month_word:
            months = _RU_MONTHS if month_word in _RU_MONTHS else _EN_MONTHS
            month = next(i for i, m in enumerate(months, 1) if m.startswith(month_word[:3]))
        else:
            month = int(groups["m"])
        if not (1 <= month <= 12 and 1 <= day_number <= 31):
            continue  # not a date at all, like «цена 12.50»
        year_text = groups.get("y")
        if year_text:
            year = int(year_text) + (2000 if len(year_text) == 2 else 0)
            found_day = _date(year, month, day_number)
        else:
            found_day = _yearly(month, day_number, date(now.year, 1, 1))
        if found_day is None:
            return None  # it looks like a date, but the calendar has no such day
        found.update(day=found_day, day_has_year=bool(year_text))
        work.take(pattern)
        break

    if "day" not in found and (match := work.take(DAY_WORD)) is not None:
        word = match.group("w")
        shift = (
            2
            if "после" in word or "after" in word
            else (1 if word in ("завтра", "tomorrow") else 0)
        )
        found["day"] = now.date() + timedelta(days=shift)

    once = "day" not in found and "repeat" not in found
    if once and (match := work.take(WEEKDAY_ONCE)) is not None:
        name = match.group("ru") or match.group("en")
        names = _RU_WEEKDAYS_ACC if match.group("ru") else _EN_WEEKDAYS
        if match.group("ru_next") or match.group("en_next"):
            next_monday = now.date() + timedelta(days=7 - now.weekday())
            found["day"] = next_monday + timedelta(days=names.index(name))
        else:
            found["weekday"] = names.index(name)

    if (match := work.take(TIME_WORD)) is not None:
        found["time"] = "12:00" if match.group("w") in ("полдень", "noon") else "00:00"
    else:
        for pattern in (TIME_EN, TIME_RU, TIME_BARE):
            match = pattern.search(work.current)
            if match is None:
                continue
            groups = match.groupdict()
            hours = int(groups.get("h") or groups.get("h2") or 0)
            minutes = int(groups.get("m") or groups.get("m2") or 0)
            meridiem = groups.get("mer") or groups.get("mer2") or groups.get("pre") or ""
            meridiem = _PART_OF_DAY.get(meridiem, meridiem.replace(".", ""))
            hhmm = _hhmm(_with_meridiem(hours, meridiem or None), minutes)
            if hhmm is not None:
                found["time"] = hhmm
                work.take(pattern)
                break

    if not found:
        return None
    return Parsed(text=work.rest(), **found)


def merge(base: Parsed, answer: Parsed) -> Parsed:
    """`base` completed by a follow-up answer («в 18», «завтра в 10», «каждый день в 9»).

    What the answer says wins; the rest of `base` stays. The text is `base`'s, unless it
    had none and the answer brings one. A one-off answer turns a repeat into a one-off,
    except a bare weekday («в среду») on a weekly repeat, which moves the repeat there.
    """
    fields: dict[str, Any] = {}
    dated = answer.delta is not None or answer.delta_days is not None or answer.day is not None
    if answer.repeat is Repeat.NONE and answer.weekday is not None and not dated:
        if base.repeat is Repeat.WEEKLY:
            fields["weekdays"] = 1 << answer.weekday
            answer = replace(answer, weekday=None)
        else:
            dated = True
    if answer.repeat is Repeat.NONE and dated:
        fields.update(repeat=Repeat.NONE, weekdays=None, interval_weeks=1, month_day=None)
    if answer.repeat is not Repeat.NONE:
        fields.update(
            repeat=answer.repeat,
            weekdays=answer.weekdays,
            interval_weeks=answer.interval_weeks,
            month_day=answer.month_day,
            day=None,
            weekday=None,
            delta=None,
            delta_days=None,
        )
    if answer.delta is not None:
        fields.update(delta=answer.delta, time=None, day=None, weekday=None, delta_days=None)
    if answer.delta_days is not None:
        fields.update(delta_days=answer.delta_days, day=None, weekday=None, delta=None)
    if answer.day is not None:
        fields.update(
            day=answer.day,
            day_has_year=answer.day_has_year,
            weekday=None,
            delta=None,
            delta_days=None,
        )
    if answer.weekday is not None:
        fields.update(weekday=answer.weekday, day=None, delta=None, delta_days=None)
    if answer.time is not None:
        fields.update(time=answer.time, delta=None)
    return replace(base, text=base.text or answer.text, **fields)


def dump(parsed: Parsed) -> dict[str, Any]:
    """A JSON-safe form, for the bot's dialog state."""
    return {
        "text": parsed.text,
        "time": parsed.time,
        "day": parsed.day.isoformat() if parsed.day else None,
        "day_has_year": parsed.day_has_year,
        "weekday": parsed.weekday,
        "delta": parsed.delta.total_seconds() if parsed.delta is not None else None,
        "delta_days": parsed.delta_days,
        "repeat": parsed.repeat.value,
        "weekdays": parsed.weekdays,
        "interval_weeks": parsed.interval_weeks,
        "month_day": parsed.month_day,
    }


def load(data: dict[str, Any]) -> Parsed:
    return Parsed(
        text=str(data["text"]),
        time=data["time"],
        day=date.fromisoformat(data["day"]) if data["day"] else None,
        day_has_year=bool(data["day_has_year"]),
        weekday=data["weekday"],
        delta=timedelta(seconds=data["delta"]) if data["delta"] is not None else None,
        delta_days=data["delta_days"],
        repeat=Repeat(data["repeat"]),
        weekdays=data["weekdays"],
        interval_weeks=int(data["interval_weeks"]),
        month_day=data["month_day"],
    )
