"""The made-up world of the README's pictures of the bot: Moscow on Wednesday, October 7, 2026,
and the week of weather from that morning.

No real chat, account or server is behind it, and nothing comes from tests/: the weather is an
Open-Meteo answer written by hand, in Unix seconds like the real one. It is imported without a
browser: scripts/forecast_card.py draws the README's forecast from it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")
DIGEST = datetime(2026, 10, 7, 8, 0, tzinfo=MOSCOW)  # the morning digest asks for the forecast
CITY = {"ru": "Москва", "en": "Moscow"}

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
