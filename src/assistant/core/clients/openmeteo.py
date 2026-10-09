"""Open-Meteo forecast and city search (no API key).

One forecast request per place carries all the bot and the app show; its answer is checked
before it is kept. At most two forecasts are asked for at once, and a failure of Open-Meteo
pauses forecasts for a minute. Every request, forecast or search, counts against a budget of
the process and of the user it is for."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from assistant.core.errors import UpstreamUnavailable
from assistant.core.ratelimit import RateLimiter
from assistant.core.timeutil import is_valid_timezone

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
# What one forecast asks for: 23 variables, 2.3 calls by Open-Meteo's count.
CURRENT = (
    "temperature_2m",
    "apparent_temperature",
    "weather_code",
    "is_day",
    "wind_speed_10m",
    "wind_gusts_10m",
    "relative_humidity_2m",
    "precipitation",
)
SERIES: dict[str, tuple[str, ...]] = {
    "minutely_15": ("precipitation",),
    "hourly": (
        "temperature_2m",
        "precipitation_probability",
        "precipitation",
        "weather_code",
        "is_day",
        "wind_speed_10m",
    ),
    "daily": (
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
        "precipitation_sum",
        "wind_speed_10m_max",
        "sunrise",
        "sunset",
    ),
}
_FORECAST_PARAMS: dict[str, str | int] = {
    "timezone": "auto",
    # Moments in Unix seconds: Open-Meteo labels the whole week with the offset in force when
    # it is asked, so its local labels would be an hour off past a change of clocks.
    "timeformat": "unixtime",
    "wind_speed_unit": "ms",
    # Whole days from today's 00:00, not forecast_hours: the evening tips compare 08:00 and
    # 18:00 of today.
    "forecast_days": 7,
    # 13 quarter-hours from the one before `current.time`. Open-Meteo aligns them to whole
    # hours of the offset, so in a zone with a half-hour offset they start up to 45 minutes
    # off; 13 still cover 15 to 120 minutes ahead.
    "past_minutely_15": 1,
    "forecast_minutely_15": 12,
    "current": ",".join(CURRENT),
    **{block: ",".join(names) for block, names in SERIES.items()},
}
DAY_SECONDS = 86_400
FORECAST_TTL = 600.0
FORECAST_PLACES = 512  # forecasts kept per process
# Forecasts asked for at once per process. The free plan runs one request per IP and queues
# four, and the bot and the API share the server's IP.
FORECAST_SLOTS = 2
PAUSE = 60.0  # seconds without forecast requests after Open-Meteo failed
SEARCH_TTL = 3600.0
SEARCH_QUERIES = 256  # searches kept per process
SEARCH_COUNT = 5  # places one geocoding request offers
# Requests to Open-Meteo, forecasts and searches together, within a sliding day. The free plan
# allows an IP under 600 calls a minute, 5 000 an hour and 10 000 a day; a forecast is 2.3 calls,
# and the bot and the API share the server's IP. A process's budget, even spent within one hour,
# keeps the two under the hourly limit (2 × 1 000 × 2.3 = 4 600) and so under the daily one, but
# only between restarts: the budgets live in the processes' memory. A user's budget keeps one
# account from spending it.
BUDGET_WINDOW = 86_400.0
PROCESS_BUDGET = 1_000
USER_BUDGET = 200
BUDGET_WARN_EVERY = 3_600.0  # seconds between two log lines about a spent process budget


@dataclass(frozen=True)
class City:
    name: str
    admin: str | None
    country: str | None
    lat: float
    lon: float
    timezone: str
    # The GeoNames id. Last and optional: the places of a search kept in a dialog's data
    # before 2.6 have none and must still load.
    geo_id: int | None = None


def check_forecast(data: object) -> dict[str, Any]:
    """`data` when the parser can read all of it, ValueError otherwise: an object with a zone
    name and an offset under a day; `current`, `hourly`, `daily` and maybe `minutely_15` as
    objects; in each series the times and every variable asked for as lists of one length;
    every value asked for null or a finite number. A variable left out counts as nulls."""
    if not isinstance(data, dict):
        raise ValueError("not an object")
    zone, offset = data.get("timezone"), data.get("utc_offset_seconds")
    if not isinstance(zone, str) or not zone:
        raise ValueError("no time zone")
    if isinstance(offset, bool) or not isinstance(offset, int) or abs(offset) >= DAY_SECONDS:
        raise ValueError("no offset under a day")
    current = data.get("current")
    if not isinstance(current, dict):
        raise ValueError("no current weather")
    if not all(_readable(current.get(name)) for name in ("time", *CURRENT)):
        raise ValueError("a current value is not a number")
    for block, names in SERIES.items():
        if block == "minutely_15" and block not in data:
            continue  # without the quarter-hours there is just no «rain soon» tip
        _check_series(data.get(block), names)
    return data


def _check_series(block: object, names: tuple[str, ...]) -> None:
    if not isinstance(block, dict):
        raise ValueError("no series")
    times = block.get("time")
    if not isinstance(times, list):
        raise ValueError("a series without times")
    for name in ("time", *names):
        if name not in block:
            continue  # left out: all nulls
        values = block[name]
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError("a series is not as long as its times")
        if not all(map(_readable, values)):
            raise ValueError("a series value is not a number")


def _readable(value: object) -> bool:
    return value is None or _number(value) is not None


def _number(value: object) -> float | None:
    """A finite number as a float; None for anything else. true and false are not numbers
    here, though Python counts them as ints."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:  # an integer too long for a float
        return None
    return number if math.isfinite(number) else None


class _Cache[K, V]:
    """Values kept for `ttl` seconds. Past `size` keys the one stored first goes: it is also
    the nearest to going stale."""

    def __init__(self, ttl: float, size: int, clock: Callable[[], float]) -> None:
        self._ttl = ttl
        self._size = size
        self._clock = clock
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        item = self._items.get(key)
        if item is None or self._clock() - item[0] >= self._ttl:
            return None
        return item[1]

    def put(self, key: K, value: V) -> None:
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        if len(self._items) > self._size:
            self._items.popitem(last=False)


class OpenMeteoClient:
    """The bot and the API keep one each. `deadline`: the seconds a forecast call may take in
    all, the wait for a slot included, and that each request of a search may take."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        deadline: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._deadline = deadline
        self._clock = clock
        self._slots = asyncio.Semaphore(FORECAST_SLOTS)
        self._resume_at = -math.inf  # forecasts are paused until this moment of `clock`
        self._forecasts: _Cache[tuple[float, float], dict[str, Any]] = _Cache(
            FORECAST_TTL, FORECAST_PLACES, clock
        )
        self._searches: _Cache[tuple[str, str], tuple[City, ...]] = _Cache(
            SEARCH_TTL, SEARCH_QUERIES, clock
        )
        self._budget = RateLimiter(PROCESS_BUDGET, BUDGET_WINDOW, clock)
        self._user_budgets = RateLimiter(USER_BUDGET, BUDGET_WINDOW, clock)
        self._warned_at = -math.inf  # when the log last told of the spent process budget

    async def forecast(
        self, lat: float, lon: float, *, user_id: int | None = None
    ) -> dict[str, Any]:
        """The forecast for the place, checked by check_forecast and at most 10 minutes old.
        Places are told apart to 0.01°, and Open-Meteo gets no more: it keeps its logs.

        UpstreamUnavailable when Open-Meteo fails, during the pause after a failure, when no
        answer comes within the deadline, and when the process's budget or that of the user
        `user_id` is spent (None: the process's alone). A kept forecast costs no budget."""
        key = (round(lat, 2), round(lon, 2))
        if (kept := self._kept(key)) is not None:
            return kept
        asked = False
        try:
            async with asyncio.timeout(self._deadline), self._slots:
                # Again with the slot: the call may have waited behind one that failed or
                # behind one that has just fetched the same place.
                if (kept := self._kept(key)) is not None:
                    return kept
                self._spend(user_id)
                asked = True
                return await self._ask(key)
        except TimeoutError as error:
            # Only an exchange that ran out of time tells about Open-Meteo; a call that got no
            # slot in time tells only about the queue.
            if asked:
                self._pause()
            raise UpstreamUnavailable(service="open-meteo") from error

    def _kept(self, key: tuple[float, float]) -> dict[str, Any] | None:
        """The fresh forecast from the cache, served during the pause too; None when the place
        is to be asked for; UpstreamUnavailable during the pause."""
        kept = self._forecasts.get(key)
        if kept is None and self._clock() < self._resume_at:
            raise UpstreamUnavailable(service="open-meteo")
        return kept

    async def _ask(self, key: tuple[float, float]) -> dict[str, Any]:
        """One exchange, never repeated. A failure on Open-Meteo's side (the network, a
        timeout, 5xx, 429, a body that is not a forecast) pauses forecasts; any other 4xx
        means the request itself is wrong, and waiting would not mend it."""
        lat, lon = key
        params = {"latitude": lat, "longitude": lon, **_FORECAST_PARAMS}
        try:
            response = await self._http.get(FORECAST_URL, params=params)
        except httpx.HTTPError as error:
            self._pause()
            raise UpstreamUnavailable(service="open-meteo") from error
        if not response.is_success:
            if response.status_code == 429 or response.is_server_error:
                self._pause()
            raise UpstreamUnavailable(service="open-meteo")
        try:
            data = check_forecast(response.json())
        except ValueError as error:  # not JSON, or not a forecast
            self._pause()
            raise UpstreamUnavailable(service="open-meteo") from error
        self._resume_at = -math.inf  # Open-Meteo answers again
        self._forecasts.put(key, data)
        return data

    def _pause(self) -> None:
        self._resume_at = self._clock() + PAUSE

    def _spend(self, user_id: int | None) -> None:
        """Count a request about to go out, against the user's budget first: one the user's
        budget refuses costs the process's nothing. UpstreamUnavailable when either is spent;
        no pause, Open-Meteo has not failed."""
        if user_id is not None and self._user_budgets.check(user_id) is not None:
            raise UpstreamUnavailable(service="open-meteo")
        if self._budget.check(0) is not None:
            now = self._clock()
            if now - self._warned_at >= BUDGET_WARN_EVERY:
                self._warned_at = now
                log.warning("Open-Meteo: this process spent its %d requests a day", PROCESS_BUDGET)
            raise UpstreamUnavailable(service="open-meteo")

    async def search(self, name: str, lang: str, *, user_id: int | None = None) -> list[City]:
        """Places called `name`, named in `lang`, only those whose time zone the server knows.
        Kept for an hour, nothing found too; UpstreamUnavailable on a failure, not kept. Every
        spelling tried spends the budgets, as a forecast does."""
        query = " ".join(name.split())
        key = (query.lower(), lang)
        found = self._searches.get(key)
        if found is None:
            found = ()
            for attempt in _attempts(query):
                found = await self._look_up(attempt, lang, user_id)
                if found:
                    break
            self._searches.put(key, found)
        return list(found)

    async def _look_up(self, name: str, lang: str, user_id: int | None) -> tuple[City, ...]:
        """One geocoding request, which spends the budgets. The geocoder is a service apart: a
        request takes no forecast slot and neither minds nor opens the pause."""
        self._spend(user_id)
        params: dict[str, str | int] = {"name": name, "count": SEARCH_COUNT, "language": lang}
        try:
            async with asyncio.timeout(self._deadline):
                response = await self._http.get(GEOCODING_URL, params=params)
            response.raise_for_status()
            return _cities(response.json())
        except (TimeoutError, httpx.HTTPError, ValueError) as error:
            raise UpstreamUnavailable(service="open-meteo") from error


def _attempts(query: str) -> list[str]:
    """What to ask the geocoder for, in turn, until it finds something. It knows
    «Санкт-Петербург» but not «Санкт Петербург», and a qualifier after the comma that it does
    not know («Paris, Xyzland») hides every place. At most four requests."""
    head, comma, rest = query.partition(",")
    head = head.strip()
    hyphened = head.replace(" ", "-")
    attempts = [query]
    if " " in head:
        attempts.append(hyphened + comma + rest)
    if comma:
        attempts += [head, hyphened]
    return [attempt for attempt in dict.fromkeys(attempts) if attempt]


def _cities(data: object) -> tuple[City, ...]:
    """The places of a geocoding answer that can be saved; ValueError when it is not one. An
    answer that has found nothing has no "results" at all."""
    if not isinstance(data, dict):
        raise ValueError("not a geocoding answer")
    results = data.get("results") or []
    if not isinstance(results, list):
        raise ValueError("not a geocoding answer")
    return tuple(city for item in results if (city := _city(item)) is not None)


def _city(item: object) -> City | None:
    """A place that can be saved, or None. One without a zone the server knows would have its
    reminders at the wrong time: it used to be saved with UTC."""
    if not isinstance(item, dict):
        return None
    name, zone = item.get("name"), item.get("timezone")
    lat, lon = _number(item.get("latitude")), _number(item.get("longitude"))
    if not (isinstance(name, str) and name and isinstance(zone, str) and is_valid_timezone(zone)):
        return None
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return City(
        name=name,
        admin=_text(item.get("admin1")),
        country=_text(item.get("country")),
        lat=lat,
        lon=lon,
        timezone=zone,
        geo_id=_geo_id(item.get("id")),
    )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _geo_id(value: object) -> int | None:
    """A GeoNames id: a positive integer that SQLite's INTEGER holds."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**63:
        return None
    return value
