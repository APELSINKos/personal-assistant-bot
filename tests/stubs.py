from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from assistant.core.clients.cbr import Point, Rate, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.errors import InvalidInput, UpstreamUnavailable

# When the stub forecast was asked for: 2026-09-28 10:00 in Moscow, a Monday.
FORECAST_NOW = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)
# The temperature of each hour of a stub day from 00:00: 5.8 at its coldest (05:00), 13.2 at its
# warmest (15:00), and 08:00 and 18:00 only 4° apart, so there is no evening tip.
DAY_TEMPERATURES = (
    7.0, 6.6, 6.3, 6.1, 5.9, 5.8, 6.0, 6.6, 7.6, 8.8, 9.9, 11.0,
    11.9, 12.6, 13.1, 13.2, 13.0, 12.4, 11.6, 10.6, 9.6, 8.8, 8.1, 7.5,
)  # fmt: skip


def forecast_payload(
    now: datetime = FORECAST_NOW,
    zone: str = "Europe/Moscow",
    *,
    temperature: float | None = 9.6,
    feels_like: float | None = 7.2,
    code: int | None = 1,
    is_day: int | None = 1,
    wind: float | None = 3.4,
    gusts: float | None = 6.1,
    humidity: float | None = 71,
    precip: float | None = 0.0,
    quarters: Sequence[float | None] | None = (0.0,) * 13,
    quarters_from: int = -15,
    days: int = 7,
) -> dict[str, Any]:
    """Open-Meteo's answer to the client's request made at `now` (aware) for a place in `zone`,
    built the way Open-Meteo builds it: Unix seconds, every label under the one offset `zone`
    has at `now`; `current` at the quarter-hour `now` falls in, with the values given; the
    millimetres of `quarters` every 15 minutes from `quarters_from` minutes after `current`
    (None: no minutely_15 block); then `days` days, and their hours, from that day's 00:00.

    The hours and days are a dry, partly cloudy week: every day as DAY_TEMPERATURES (5.8…13.2),
    daylight from 07:00 to 18:00, sunrise 06:40, sunset 18:40. A test changes single values in
    the dict; on the first day of a zone that does not change its clocks, hourly[k] is k:00."""
    offset = now.astimezone(ZoneInfo(zone)).utcoffset() or timedelta(0)
    fixed = timezone(offset)
    midnight = int(datetime.combine(now.astimezone(fixed).date(), time(0), fixed).timestamp())
    current = int(now.timestamp()) // 900 * 900
    hours = range(24 * days)
    starts = [midnight + day * 86400 for day in range(days)]
    data: dict[str, Any] = {
        "utc_offset_seconds": int(offset.total_seconds()),
        "timezone": zone,
        "current": {
            "time": current,
            "interval": 900,
            "temperature_2m": temperature,
            "apparent_temperature": feels_like,
            "weather_code": code,
            "is_day": is_day,
            "wind_speed_10m": wind,
            "wind_gusts_10m": gusts,
            "relative_humidity_2m": humidity,
            "precipitation": precip,
        },
        "hourly": {
            "time": [midnight + hour * 3600 for hour in hours],
            "temperature_2m": [DAY_TEMPERATURES[hour % 24] for hour in hours],
            "precipitation_probability": [0 for _ in hours],
            "precipitation": [0.0 for _ in hours],
            "weather_code": [1 for _ in hours],
            "is_day": [int(7 <= hour % 24 <= 18) for hour in hours],
            "wind_speed_10m": [3.4 for _ in hours],
        },
        "daily": {
            "time": starts,
            "weather_code": [1] * days,
            "temperature_2m_max": [13.2] * days,
            "temperature_2m_min": [5.8] * days,
            "precipitation_probability_max": [0] * days,
            "precipitation_sum": [0.0] * days,
            "wind_speed_10m_max": [5.2] * days,
            "sunrise": [start + 6 * 3600 + 40 * 60 for start in starts],
            "sunset": [start + 18 * 3600 + 40 * 60 for start in starts],
        },
    }
    if quarters is not None:
        first = current + quarters_from * 60
        data["minutely_15"] = {
            "time": [first + step * 900 for step in range(len(quarters))],
            "precipitation": list(quarters),
        }
    return data


class StubMeteo:
    def __init__(self) -> None:
        self.forecast_data: dict[str, Any] = forecast_payload()
        self.cities: list[City] = []
        self.fail = False
        self.searches: list[tuple[str, str]] = []
        self.user_ids: list[int | None] = []  # whose budget each forecast and search spent

    async def forecast(
        self, lat: float, lon: float, *, user_id: int | None = None
    ) -> dict[str, Any]:
        self.user_ids.append(user_id)
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.forecast_data

    async def search(self, name: str, lang: str, *, user_id: int | None = None) -> list[City]:
        self.searches.append((name, lang))
        self.user_ids.append(user_id)
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.cities


class StubCbr:
    def __init__(self) -> None:
        self.fail = False
        self.history_fail = False

    async def daily(self) -> Rates:
        if self.fail:
            raise UpstreamUnavailable(service="cbr")
        usd, eur = Rate(84.1975, -0.3118), Rate(96.6671, -0.8313)
        return Rates(
            date(2026, 9, 28),
            usd,
            eur,
            {"USD": usd, "EUR": eur},
            {"USD": "R01235", "EUR": "R01239"},
        )

    async def history(self, code: str, days: int = 30) -> list[Point]:
        if self.fail or self.history_fail:
            raise UpstreamUnavailable(service="cbr")
        if code not in ("USD", "EUR"):
            raise LookupError(code)
        base = 84.0 if code == "USD" else 96.0
        return [Point(date(2026, 9, 1) + timedelta(days=i), base + i / 10) for i in range(20)]


class StubCalendars:
    """Calendars by URL; a URL it does not know answers like a dead link."""

    def __init__(self) -> None:
        self.bodies: dict[str, bytes] = {}
        self.errors: dict[str, str] = {}  # URL → the reason of InvalidInput(field="url")
        self.requests: list[str] = []

    async def fetch(self, url: str) -> bytes:
        self.requests.append(url)
        if url in self.errors:
            raise InvalidInput(field="url", reason=self.errors[url])
        if url not in self.bodies:
            raise InvalidInput(field="url", reason="unreachable")
        return self.bodies[url]

    async def head(self, url: str, limit: int = 4096) -> bytes:
        return (await self.fetch(url))[:limit]
