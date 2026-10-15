"""The made-up world of the README's pictures of the bot (spec §13.6): Moscow on Wednesday,
October 7, 2026, the week of weather from that morning, and «Саша» / «Alex», who has used the bot
for a while — two habits with months of marks, a pinned shopping list, October's spending, a
workout for the evening and two classes of the fictional group «ДЕМО-01-26».

No real chat, account or server is behind it, and nothing comes from tests/: the weather is an
Open-Meteo answer written by hand, in Unix seconds like the real one, and the bank's rates are
made up as well. The settings give every field, so neither .env nor the developer's environment
reaches the bot. It is imported without a browser: scripts/forecast_card.py draws the README's
forecast from it, and chats.py records the chats in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.cbr import Point, Rate, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.config import Settings
from assistant.core.errors import InvalidInput, UpstreamUnavailable
from assistant.core.models import HabitMark, Lesson, ScheduleKind, ScheduleSource, User, WeekLabel
from assistant.core.services import habits, money, notes, reminders

MOSCOW = ZoneInfo("Europe/Moscow")
# The chats' clock, in its order: the digest; the user writes; the evening's workout goes, in no
# picture; the reminder made at noon fires the next morning.
DIGEST = datetime(2026, 10, 7, 8, 0, tzinfo=MOSCOW)  # the morning digest asks for the forecast
PHRASES = datetime(2026, 10, 7, 12, 40, tzinfo=MOSCOW)
EVENING = datetime(2026, 10, 7, 19, 0, tzinfo=MOSCOW)
NEXT_MORNING = datetime(2026, 10, 8, 7, 30, tzinfo=MOSCOW)
CITY = {"ru": "Москва", "en": "Moscow"}
LAT, LON = 55.75204, 37.61781

# Wednesday hour by hour from 00:00: a cold, overcast morning, +6 at the digest and +13 in the
# afternoon, so the evening is warmer than the morning.
WEDNESDAY = (
    6.4, 6.0, 5.6, 5.2, 4.9, 4.6, 4.7, 5.1, 5.8, 7.4, 9.6, 11.0,
    12.1, 12.8, 13.1, 13.2, 12.9, 12.2, 11.4, 10.2, 9.4, 8.8, 8.3, 7.9,
)  # fmt: skip
# Its rain after 18:00, by the hour's label: (chance, mm) of the hour before it. Earlier the
# chance is 5 % and it is dry.
WEDNESDAY_RAIN = {
    16: (20, 0.0), 17: (40, 0.0), 18: (55, 0.0), 19: (80, 0.6),
    20: (80, 1.1), 21: (75, 0.9), 22: (70, 0.7), 23: (60, 0.4),
}  # fmt: skip
# The week from Wednesday: (WMO code, lowest, highest, chance of rain or snow, strongest wind).
# Rain tonight, cloudy and then sunny days, drizzle on Sunday, fog on Monday, wet snow on Tuesday.
WEEK = (
    (61, 4.6, 13.2, 80, 4.8),
    (3, 5.1, 10.6, 20, 5.2),
    (2, 3.4, 11.8, 10, 3.9),
    (0, 1.6, 12.4, 0, 3.1),
    (53, 6.2, 10.1, 70, 6.2),
    (45, 4.0, 8.3, 15, 2.7),
    (71, -1.2, 3.4, 60, 7.4),
)


@dataclass(frozen=True)
class Hour:
    at: datetime  # the label
    temperature: float
    chance: int  # of rain or snow, in the hour before the label
    code: int
    daylight: int  # Open-Meteo's is_day
    mm: float
    wind: float


def _stamp(moment: datetime) -> int:
    return int(moment.timestamp())


def _swing(hour: int) -> float:
    """From -1 at 03:00 to 1 at 15:00: the course of a day's temperature and wind."""
    return math.cos(2 * math.pi * (hour - 15) / 24)


def _sun(day: int) -> tuple[datetime, datetime]:
    """Sunrise and sunset in Moscow in October: two minutes later and three earlier every day."""
    midnight = DIGEST.replace(hour=0) + timedelta(days=day)
    rise = midnight + timedelta(hours=7, minutes=12 + 2 * day)
    return rise, midnight + timedelta(hours=18, minutes=6 - 3 * day)


def _hour(index: int) -> Hour:
    """The hour `index` from Wednesday's 00:00. Another day runs from its lowest at 03:00 to its
    highest at 15:00, rains a little all day when its chance is 50 % or more, and keeps its
    code."""
    day, hour = divmod(index, 24)
    code, low, high, chance, wind = WEEK[day]
    at = DIGEST.replace(hour=0) + timedelta(hours=index)
    if day == 0:
        temperature = WEDNESDAY[hour]
        chance, mm = WEDNESDAY_RAIN.get(hour, (5, 0.0))
        code = code if mm else 3  # overcast until the rain
    else:
        temperature = round((low + high) / 2 + (high - low) / 2 * _swing(hour), 1)
        mm = 0.2 if chance >= 50 else 0.0
    rise, sunset = _sun(day)
    return Hour(
        at=at,
        temperature=temperature,
        chance=chance,
        code=code,
        daylight=int(rise <= at < sunset),
        mm=mm,
        wind=round(wind * (0.75 + 0.25 * _swing(hour)), 1),
    )


def forecast_answer() -> dict[str, Any]:
    """Open-Meteo's answer for Moscow to the bot's request at DIGEST: what the client asks for
    (core/clients/openmeteo.py), the week from Wednesday's 00:00 and the values now at the
    digest's quarter-hour."""
    hours = [_hour(index) for index in range(24 * len(WEEK))]
    days = range(len(WEEK))
    now = hours[DIGEST.hour]  # the digest is on Wednesday, on the hour
    return {
        "utc_offset_seconds": 3 * 3600,
        "timezone": "Europe/Moscow",
        "current": {
            "time": _stamp(DIGEST),
            "interval": 900,
            "temperature_2m": now.temperature,
            "apparent_temperature": 3.1,
            "weather_code": now.code,
            "is_day": now.daylight,
            "wind_speed_10m": now.wind,
            "wind_gusts_10m": 7.2,
            "relative_humidity_2m": 84,
            "precipitation": 0.0,
        },
        "minutely_15": {  # from a quarter-hour before now, two dry hours ahead
            "time": [_stamp(DIGEST) + 900 * (step - 1) for step in range(13)],
            "precipitation": [0.0] * 13,
        },
        "hourly": {
            "time": [_stamp(hour.at) for hour in hours],
            "temperature_2m": [hour.temperature for hour in hours],
            "precipitation_probability": [hour.chance for hour in hours],
            "precipitation": [hour.mm for hour in hours],
            "weather_code": [hour.code for hour in hours],
            "is_day": [hour.daylight for hour in hours],
            "wind_speed_10m": [hour.wind for hour in hours],
        },
        "daily": {
            "time": [_stamp(hours[24 * day].at) for day in days],
            "weather_code": [WEEK[day][0] for day in days],
            "temperature_2m_max": [WEEK[day][2] for day in days],
            "temperature_2m_min": [WEEK[day][1] for day in days],
            "precipitation_probability_max": [WEEK[day][3] for day in days],
            "precipitation_sum": [
                round(sum(hour.mm for hour in hours[24 * day : 24 * day + 24]), 1) for day in days
            ],
            "wind_speed_10m_max": [WEEK[day][4] for day in days],
            "sunrise": [_stamp(_sun(day)[0]) for day in days],
            "sunset": [_stamp(_sun(day)[1]) for day in days],
        },
    }


# The user, the names of the demo (spec §17: no real person) and the numbers of their own.
USER = 1
NAME = {"ru": "Саша", "en": "Alex"}
BUDGET = 3_000_000  # 30 000 ₽ a month, in hundredths
# «Спорт» every day since August: a miss now and then, a few days left unmarked, and today not
# marked yet, so the strip of nine days ends with a run of five.
SPORT = {"ru": "Спорт", "en": "Sport"}
SPORT_SINCE = date(2026, 8, 3)
SPORT_MISSED = (
    date(2026, 8, 9), date(2026, 8, 21), date(2026, 9, 2),
    date(2026, 9, 14), date(2026, 9, 26), date(2026, 10, 1),
)  # fmt: skip
SPORT_UNMARKED = (date(2026, 8, 15), date(2026, 9, 6), date(2026, 9, 20))
# «Бассейн» three times a week since the term began: the goal met for three weeks running, one
# swim so far this week. The list shows it as a week's progress, «Спорт» as days.
SWIMMING = {"ru": "Бассейн", "en": "Swimming"}
SWIMMING_SINCE = date(2026, 8, 31)
SWIMS = (
    date(2026, 8, 31), date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 12),
    date(2026, 9, 14), date(2026, 9, 16), date(2026, 9, 18), date(2026, 9, 21), date(2026, 9, 24),
    date(2026, 9, 26), date(2026, 9, 29), date(2026, 10, 1), date(2026, 10, 3), date(2026, 10, 5),
)  # fmt: skip
SWIMMING_MISSED = (date(2026, 9, 10),)
SHOPPING = {
    "ru": ("Покупки", ("молоко", "хлеб", "яйца")),
    "en": ("Shopping", ("milk", "bread", "eggs")),
}
WORKOUT = {"ru": "тренировка", "en": "workout"}  # today at 19:00
# October before «кофе 250»: 23 600 ₽, 79 % of the budget, so the coffee (23 850 ₽) stays short of
# the 80 % warning at 24 000 ₽. The rent of the 1st is the one large payment; the other days are
# ordinary, yesterday's 2 040 ₽ among them, which the digest shows.
# (day, preset, roubles, (the note in Russian, in English))
OCTOBER = (
    (1, "home", 12_000, ("квартира", "rent")),
    (1, "groceries", 1_350, ("продукты", "groceries")),
    (2, "cafe", 520, ("обед", "lunch")),
    (2, "groceries", 1_350, ("продукты", "groceries")),
    (3, "fun", 1_600, ("кино", "cinema")),
    (3, "cafe", 860, ("обед", "lunch")),
    (4, "groceries", 1_650, ("продукты", "groceries")),
    (5, "transport", 1_400, ("такси", "taxi")),
    (5, "phone", 830, ("связь", "phone")),
    (6, "cafe", 640, ("обед", "lunch")),
    (6, "groceries", 1_400, ("продукты", "groceries")),
)
# «Группа МИРЭА»: the demo's fictional group and its Wednesday, the term's sixth week. In English
# the subjects are English, the rooms in Latin letters and the kinds of class left out, as in the
# demo. (start, end, kind, subject, room)
GROUP = {"ru": "ДЕМО-01-26", "en": "DEMO-01-26"}
WEEK_LABEL = {"ru": "6 неделя", "en": "Week 6"}
CLASSES = {
    "ru": (
        ("10:40", "12:10", "ЛК", "Математический анализ", "А-16"),
        ("12:40", "14:10", "ПР", "Разработка баз данных", "И-212-б"),
    ),
    "en": (
        ("10:40", "12:10", None, "Calculus", "A-16"),
        ("12:40", "14:10", None, "Databases", "I-212-b"),
    ),
}
DOLLAR, EURO = Rate(81.4675, -0.2349), Rate(94.8312, 0.1708)


def settings() -> Settings:
    """The bot's settings in the world: every field given, since an argument wins over the
    environment, and .env left unread. A developer's .env holds the bot's token and the app's
    address, which would put «📱 Открыть приложение» under the welcome and «Мой день»."""
    return Settings(
        _env_file=None,
        bot_token="123456:SHOWCASE",
        database_url="sqlite+aiosqlite://",
        webapp_url=None,
        default_city=CITY["ru"],
        default_lat=LAT,
        default_lon=LON,
        default_timezone="Europe/Moscow",
        default_morning_time="08:00",
        log_level="WARNING",
        http_timeout=10.0,
        scheduler_interval=20.0,
        api_host="127.0.0.1",
        api_port=8000,
        api_rate_limit=120,
        api_docs=False,
        mirea_directory=False,
    )


class Weather:
    """Open-Meteo for the bot: the week above wherever it is asked about. No search."""

    async def forecast(
        self, lat: float, lon: float, *, user_id: int | None = None
    ) -> dict[str, Any]:
        return forecast_answer()

    async def search(self, name: str, lang: str, *, user_id: int | None = None) -> list[City]:
        raise UpstreamUnavailable(service="open-meteo")


class Bank:
    """The Central Bank: the dollar and the euro of the morning. No history."""

    async def daily(self) -> Rates:
        return Rates(DIGEST.date(), DOLLAR, EURO, {"USD": DOLLAR, "EUR": EURO})

    async def history(self, code: str, days: int = 30) -> list[Point]:
        raise UpstreamUnavailable(service="cbr")


class Calendars:
    """No calendar can be fetched: the group's classes are in the database already."""

    async def fetch(self, url: str) -> bytes:
        raise InvalidInput(field="url", reason="unreachable")

    async def head(self, url: str, limit: int = 4096) -> bytes:
        raise InvalidInput(field="url", reason="unreachable")


def _moment(day: date, hour: int = 9) -> datetime:
    """A moment of the day in Moscow, for what the user did before the pictures."""
    return datetime.combine(day, time(hour), MOSCOW)


async def seed(session: AsyncSession, lang: str) -> None:
    """The user's world in `lang`, written into an empty database through the bot's own services
    where it has them: what the user had done before the morning of the digest."""
    user = User(
        id=USER,
        first_name=NAME[lang],
        tg_language=lang,
        city=CITY[lang],
        lat=LAT,
        lon=LON,
        timezone="Europe/Moscow",
        morning_enabled=True,
        morning_time="08:00",
        can_write=True,
        money_budget=BUDGET,
    )
    session.add(user)
    await session.flush()
    sport = await habits.create(session, user, SPORT[lang], _moment(SPORT_SINCE), emoji="💪")
    day = SPORT_SINCE
    while day < DIGEST.date():
        if day not in SPORT_UNMARKED:
            session.add(HabitMark(habit_id=sport.id, day=day, done=day not in SPORT_MISSED))
        day += timedelta(days=1)
    swimming = await habits.create(
        session,
        user,
        SWIMMING[lang],
        _moment(SWIMMING_SINCE),
        emoji="🏊",
        color="sky",
        weekly_goal=3,
    )
    for day in SWIMS:
        session.add(HabitMark(habit_id=swimming.id, day=day, done=True))
    for day in SWIMMING_MISSED:
        session.add(HabitMark(habit_id=swimming.id, day=day, done=False))
    title, items = SHOPPING[lang]
    await notes.create(
        session, user.id, title, items, pinned=True, now=_moment(date(2026, 10, 6), 20)
    )
    presets = {category.preset: category for category in await money.categories(session, user)}
    for number, preset, roubles, (russian, english) in OCTOBER:
        await money.add_entry(
            session,
            user,
            amount=roubles * 100,
            category_id=presets[preset].id,
            note=russian if lang == "ru" else english,
            day=date(2026, 10, number),
            now=DIGEST,
        )
    evening = EVENING.replace(tzinfo=None)
    await reminders.create(session, user, WORKOUT[lang], evening, _moment(date(2026, 10, 6), 21))
    fetched = _moment(DIGEST.date(), 6)
    session.add(
        ScheduleSource(
            user_id=user.id,
            kind=ScheduleKind.MIREA,
            title=GROUP[lang],
            fetched_at=fetched,
            ok_at=fetched,
            next_refresh_at=fetched + timedelta(hours=6),
        )
    )
    for start, end, kind, subject, room in CLASSES[lang]:
        session.add(
            Lesson(
                user_id=user.id,
                uid=f"{subject}@showcase",
                starts_at=datetime.combine(DIGEST.date(), time.fromisoformat(start), MOSCOW),
                ends_at=datetime.combine(DIGEST.date(), time.fromisoformat(end), MOSCOW),
                title=subject,
                kind=kind,
                room=room,
            )
        )
    monday = date(2026, 10, 5)
    session.add(
        WeekLabel(
            user_id=user.id,
            start_date=monday,
            end_date=monday + timedelta(days=7),
            label=WEEK_LABEL[lang],
        )
    )
    await session.flush()
