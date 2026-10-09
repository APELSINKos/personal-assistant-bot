"""The forecast of a place and the 'smart' tips shown in the bot and the Mini App.

Open-Meteo answers in Unix seconds and labels the whole week with the one offset in force when it
is asked, so its own local labels would be an hour off past a change of clocks. Moments are
therefore turned into the place's wall clock through `Forecast.tz` alone, a day's date comes
from its label and the answer's offset, and the hours of a day are found by their moment, never
by their place in a list. Outwards the service gives naive local time of the place.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.timeutil import SUPPORTED_YEARS, is_valid_timezone

_CODES: tuple[tuple[int, int, str, str], ...] = (
    (0, 0, "☀️", "wmo-clear"),
    (1, 2, "🌤", "wmo-partly"),
    (3, 3, "☁️", "wmo-cloudy"),
    (45, 48, "🌫", "wmo-fog"),
    (51, 57, "🌦", "wmo-drizzle"),
    (61, 67, "🌧", "wmo-rain"),
    (71, 77, "🌨", "wmo-snow"),
    (80, 82, "🌧", "wmo-showers"),
    (85, 86, "🌨", "wmo-snowfall"),
    (95, 99, "⛈", "wmo-storm"),
)
NO_CODE = -1  # the code of an hour, a day or of now that came without one: «нет данных»
NIGHT_ICON = "🌙"  # instead of the sun of a clear or partly cloudy sky at night
HOUR = timedelta(hours=1)
# A chance of rain or snow is worth a mention from this many percent on: in the bot, on the
# forecast picture and in the app (shownChance).
CHANCE_SHOWN = 20
# The classes line mentions rain or snow on the way from this chance on.
CLASSES_CHANCE = 30


@dataclass(frozen=True)
class Tip:
    key: str
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WeatherNow:
    city: str
    temperature: float | None
    feels_like: float | None
    wind: float | None
    code: int
    tmin: float | None  # today's range: the day of `at`
    tmax: float | None
    tips: list[Tip]
    is_day: bool = True
    gusts: float | None = None
    humidity: float | None = None  # percent
    precip: float | None = None  # mm in the last quarter-hour: rain or snow right now
    at: datetime | None = None  # the time of these values on the place's clock


@dataclass(frozen=True)
class Hour:
    at: datetime  # the label, on the place's clock
    temperature: float  # at the label, like `code`
    code: int
    is_day: bool
    precip_chance: int | None  # percent, of the hour before the label: 16:00 tells of 15:00–16:00
    precip: float | None  # mm in the hour before the label
    wind: float | None


@dataclass(frozen=True)
class Day:
    day: date
    code: int  # the day's heaviest weather, as Open-Meteo picks it
    tmin: float
    tmax: float
    precip_chance: int | None  # percent, the highest of the day's hours
    precip_sum: float | None  # mm
    wind_max: float | None
    sunrise: datetime | None  # on the place's clock; see polar()
    sunset: datetime | None


@dataclass(frozen=True)
class Forecast:
    now: WeatherNow
    quarters: list[tuple[datetime, float | None]]  # mm of rain or snow every 15 minutes
    hours: list[Hour]  # a week from the first day's 00:00
    days: list[Day]
    zone: str  # the place's time zone as Open-Meteo names it, for showing
    tz: tzinfo  # the only way from a moment to the place's clock


@dataclass(frozen=True)
class ClassesWeather:
    """The way to the first class and home after the last one."""

    start: datetime  # the first class begins, on the user's clock
    start_temp: float | None  # None: the forecast has no hour for the start
    start_chance: int | None  # None under CLASSES_CHANCE as well
    end: datetime  # the last class ends
    end_temp: float | None
    end_chance: int | None


def describe(code: int, is_day: bool = True) -> tuple[str, str]:
    """The icon and the key of the words for a WMO code. At night a clear or partly cloudy sky
    shows the moon and keeps its words. An unknown code, NO_CODE included, is «нет данных»: a
    missing code says nothing about rain."""
    for first, last, emoji, key in _CODES:
        if first <= code <= last:
            return (NIGHT_ICON if not is_day and code <= 2 else emoji), key
    return "🌡", "wmo-unknown"


def parse(data: Mapping[str, Any], city: str) -> Forecast:
    """The forecast in an answer that check_forecast has passed; `city` names `now`. A value the
    answer has as null, or a moment that is not a time of SUPPORTED_YEARS, counts as missing: an
    hour without its time or temperature and a day without its time, minimum or maximum are left
    out, since Open-Meteo's last day may come empty."""
    zone: str = data["timezone"]
    offset = timezone(timedelta(seconds=data["utc_offset_seconds"]))
    # A zone the server's tzdb does not know is read with the answer's offset, as Open-Meteo
    # labels it.
    tz: tzinfo = ZoneInfo(zone) if is_valid_timezone(zone) else offset
    days = _days(data["daily"], tz, offset)
    now = _now(data["current"], city, tz, days)
    forecast = Forecast(
        now=now,
        quarters=_quarters(data.get("minutely_15"), tz),
        hours=_hours(data["hourly"], tz),
        days=days,
        zone=zone,
        tz=tz,
    )
    return replace(forecast, now=replace(now, tips=build_tips(forecast)))


def _now(current: Mapping[str, Any], city: str, tz: tzinfo, days: list[Day]) -> WeatherNow:
    at = _moment(current.get("time"), tz)
    if at is not None:
        today = next((day for day in days if day.day == at.date()), None)
    else:  # without the time, the first day, where Open-Meteo starts
        today = days[0] if days else None
    return WeatherNow(
        city=city,
        temperature=_num(current.get("temperature_2m")),
        feels_like=_num(current.get("apparent_temperature")),
        wind=_num(current.get("wind_speed_10m")),
        code=_code(current.get("weather_code")),
        tmin=today.tmin if today is not None else None,
        tmax=today.tmax if today is not None else None,
        tips=[],
        is_day=_is_day(current.get("is_day")),
        gusts=_num(current.get("wind_gusts_10m")),
        humidity=_num(current.get("relative_humidity_2m")),
        precip=_num(current.get("precipitation")),
        at=at,
    )


def _quarters(block: object, tz: tzinfo) -> list[tuple[datetime, float | None]]:
    if not isinstance(block, Mapping):
        return []  # Open-Meteo may leave them out: then there is no «rain soon»
    steps = ((_moment(stamp, tz), _num(amount)) for stamp, amount in _rows(block, "precipitation"))
    return [(at, amount) for at, amount in steps if at is not None]


def _hours(block: Mapping[str, Any], tz: tzinfo) -> list[Hour]:
    hours: list[Hour] = []
    names = (
        "temperature_2m",
        "weather_code",
        "is_day",
        "precipitation_probability",
        "precipitation",
        "wind_speed_10m",
    )
    for stamp, temperature, code, is_day, chance, precip, wind in _rows(block, *names):
        at, degrees = _moment(stamp, tz), _num(temperature)
        if at is None or degrees is None:
            continue
        hours.append(
            Hour(
                at=at,
                temperature=degrees,
                code=_code(code),
                is_day=_is_day(is_day),
                precip_chance=_chance(chance),
                precip=_num(precip),
                wind=_num(wind),
            )
        )
    return hours


def _days(block: Mapping[str, Any], tz: tzinfo, offset: tzinfo) -> list[Day]:
    days: list[Day] = []
    names = (
        "weather_code",
        "temperature_2m_min",
        "temperature_2m_max",
        "precipitation_probability_max",
        "precipitation_sum",
        "wind_speed_10m_max",
        "sunrise",
        "sunset",
    )
    for stamp, code, low, high, chance, total, wind, sunrise, sunset in _rows(block, *names):
        # A day's label is its 00:00 under the answer's offset. Read through the zone, a label
        # past a change of clocks would be 23:00 of the day before.
        midnight, tmin, tmax = _moment(stamp, offset), _num(low), _num(high)
        if midnight is None or tmin is None or tmax is None:
            continue
        days.append(
            Day(
                day=midnight.date(),
                code=_code(code),
                tmin=tmin,
                tmax=tmax,
                precip_chance=_chance(chance),
                precip_sum=_num(total),
                wind_max=_num(wind),
                sunrise=_moment(sunrise, tz),
                sunset=_moment(sunset, tz),
            )
        )
    return days


def _rows(block: Mapping[str, Any], *names: str) -> Iterator[tuple[Any, ...]]:
    """The steps of a series: the time, then the named values. A variable the answer left out
    is all nulls."""
    times: list[Any] = block.get("time") or []
    columns = [block.get(name) or [None] * len(times) for name in names]
    return zip(times, *columns, strict=True)


def _moment(value: object, tz: tzinfo) -> datetime | None:
    """Unix seconds as the wall clock of `tz`; None for anything that is not such a time."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        moment = datetime.fromtimestamp(value, tz)
    except (OverflowError, OSError, ValueError):  # NaN, or out of what the platform can hold
        return None
    return moment.replace(tzinfo=None) if moment.year in SUPPORTED_YEARS else None


def _num(value: object) -> float | None:
    """A finite number as a float; None for anything else, true and false included."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:  # an integer too long for a float
        return None
    return number if math.isfinite(number) else None


def _code(value: object) -> int:
    number = _num(value)
    return int(number) if number is not None else NO_CODE


def _chance(value: object) -> int | None:
    """A chance in whole percent, half up; None, not 0, when Open-Meteo has none."""
    number = _num(value)
    return math.floor(number + 0.5) if number is not None else None


def _is_day(value: object) -> bool:
    """Open-Meteo's is_day is 1 by day and 0 at night; without it, day."""
    return _num(value) != 0


def build_tips(forecast: Forecast) -> list[Tip]:
    now = forecast.now
    if now.at is None:
        return [Tip("tip-calm")]
    precip = now.precip or 0.0
    kind = "snow" if now.temperature is not None and now.temperature <= 0 else "rain"
    tips: list[Tip] = []

    soon = False
    if precip >= 0.1:
        tips.append(Tip("tip-precip-now", {"kind": kind}))
        soon = True
    else:
        # By the time of each quarter-hour: the steps start up to an hour before now (zones
        # with a half-hour offset) or after it, and run past two hours.
        for moment, amount in forecast.quarters:
            minutes = int((moment - now.at).total_seconds() // 60)
            if 0 < minutes <= 120 and amount is not None and amount >= 0.1:
                tips.append(Tip("tip-precip-soon", {"kind": kind, "minutes": minutes}))
                soon = True
                break

    today = [hour for hour in forecast.hours if hour.at.date() == now.at.date()]
    later = False
    if not soon:
        for hour in today:
            chance = hour.precip_chance
            # A chance is about the hour before its label: 17:00 says «after 16:00».
            start = hour.at - HOUR
            if start > now.at and chance is not None and chance >= 60:
                label = start.strftime("%H:%M")
                tips.append(Tip("tip-precip-later", {"kind": kind, "hour": label}))
                later = True
                break

    morning, evening = _temperature_at(today, 8), _temperature_at(today, 18)
    if morning is not None and evening is not None:
        if evening - morning >= 5:
            tips.append(Tip("tip-warmer-evening"))
        elif evening - morning <= -5:
            tips.append(Tip("tip-colder-evening"))
    wind, feels = now.wind, now.feels_like
    if wind is not None and wind >= 10:
        tips.append(Tip("tip-wind"))
    if feels is not None and feels <= -15:
        tips.append(Tip("tip-frost"))
    if feels is not None and feels >= 30:
        tips.append(Tip("tip-heat"))
    calm_wind = wind is not None and wind < 7
    if not (soon or later) and now.tmax is not None and 12 <= now.tmax <= 28 and calm_wind:
        tips.append(Tip("tip-bike"))
    return tips or [Tip("tip-calm")]


def _temperature_at(hours: list[Hour], hour: int) -> float | None:
    return next((item.temperature for item in hours if item.at.hour == hour), None)


async def forecast(
    meteo: OpenMeteoClient, city: str, lat: float, lon: float, *, user_id: int | None = None
) -> Forecast:
    """The forecast of the place named `city`: the one way in for the bot, the API and the
    digest. UpstreamUnavailable as OpenMeteoClient.forecast, which spends the budget of the
    user `user_id`."""
    return parse(await meteo.forecast(lat, lon, user_id=user_id), city)


async def current(meteo: OpenMeteoClient, city: str, lat: float, lon: float) -> WeatherNow:
    return (await forecast(meteo, city, lat, lon)).now


# The time of a forecast. `local` below is the place's wall clock without tzinfo (local_now),
# what the hours and days are compared with.


def local_now(forecast: Forecast, now: datetime) -> datetime:
    """The moment `now` (aware) on the clock of the forecast's place."""
    if now.tzinfo is None:
        raise ValueError("expected an aware datetime")
    return now.astimezone(forecast.tz).replace(tzinfo=None)


def next_hours(forecast: Forecast, local: datetime, count: int) -> list[Hour]:
    """The first `count` hours after `local`; fewer near the end of the week."""
    return [hour for hour in forecast.hours if hour.at > local][:count]


def days_from(forecast: Forecast, today: date, count: int = 7) -> list[Day]:
    """Up to `count` days from `today` on. Just after midnight a forecast kept from yesterday
    still starts with yesterday, and then the week has six days."""
    return [day for day in forecast.days if day.day >= today][:count]


def hour_of(forecast: Forecast, local: datetime) -> Hour | None:
    """The hour `local` falls in: the label at `local` or less than an hour before it (09:00 →
    09:00, 16:20 → 16:00). Its temperature and code are the ones at the label."""
    return next((hour for hour in forecast.hours if hour.at <= local < hour.at + HOUR), None)


def chance_after(forecast: Forecast, local: datetime) -> int | None:
    """The chance of rain or snow in the hour that holds `local`. A label tells of the hour
    before it, so this is the label at `local` rounded up to the hour: 09:00 → 09:00 (the way
    08:00–09:00), 16:20 → 17:00 (16:20–17:00)."""
    label = next((hour for hour in forecast.hours if local <= hour.at < local + HOUR), None)
    return label.precip_chance if label is not None else None


def chance_on_the_way_back(forecast: Forecast, local: datetime) -> int | None:
    """The chance of rain or snow on the way back from classes that end at `local`: the first
    label after the end, whose hour holds the time just after it — 16:20 → 17:00 (16:20–17:00),
    17:00 → 18:00. The label 17:00 itself tells of 16:00–17:00, the last hour of class."""
    label = next((hour for hour in forecast.hours if local < hour.at <= local + HOUR), None)
    return label.precip_chance if label is not None else None


def tomorrow(forecast: Forecast, today: date) -> Day | None:
    following = today + timedelta(days=1)
    return next((day for day in forecast.days if day.day == following), None)


def polar(day: Day) -> str | None:
    """The polar "night" (the sun does not rise) or "day" (it does not set), else None. On such
    days Open-Meteo gives midnights, not nulls: a sunrise equal to the sunset, or a sunset a
    whole day after the sunrise."""
    if day.sunrise is None or day.sunset is None:
        return None
    if day.sunrise == day.sunset:
        return "night"
    if day.sunset - day.sunrise >= timedelta(days=1):
        return "day"
    return None


def classes_weather(
    forecast: Forecast, starts_at: datetime, ends_at: datetime, user_tz: str
) -> ClassesWeather | None:
    """The weather of the way to the classes and back: the first class begins at `starts_at`,
    the last ends at `ends_at` (aware moments). Their hours are found on the clock of the
    forecast, the times are shown on the user's. The whole day's answer, whatever the time now:
    the caller drops what is over. None without an hour for the end; without one for the start,
    there is no part about the way there."""
    start, end = local_now(forecast, starts_at), local_now(forecast, ends_at)
    last = hour_of(forecast, end)
    if last is None:
        return None
    first = hour_of(forecast, start)
    zone = ZoneInfo(user_tz)
    return ClassesWeather(
        start=starts_at.astimezone(zone).replace(tzinfo=None),
        start_temp=first.temperature if first is not None else None,
        start_chance=_worth_saying(chance_after(forecast, start)) if first is not None else None,
        end=ends_at.astimezone(zone).replace(tzinfo=None),
        end_temp=last.temperature,
        end_chance=_worth_saying(chance_on_the_way_back(forecast, end)),
    )


def _worth_saying(chance: int | None) -> int | None:
    return chance if chance is not None and chance >= CLASSES_CHANCE else None
