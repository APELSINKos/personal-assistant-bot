from __future__ import annotations

from datetime import date
from typing import Any

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.errors import InvalidInput, UpstreamUnavailable


class StubMeteo:
    def __init__(self) -> None:
        self.forecast_data: dict[str, Any] = {
            "current": {
                "time": "2026-09-28T10:00",
                "temperature_2m": 9.6,
                "apparent_temperature": 7.2,
                "weather_code": 1,
                "wind_speed_10m": 3.4,
                "precipitation": 0,
            },
            "daily": {"temperature_2m_max": [13.2], "temperature_2m_min": [5.8]},
        }
        self.cities: list[City] = []
        self.fail = False
        self.searches: list[tuple[str, str]] = []

    async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.forecast_data

    async def search(self, name: str, lang: str, count: int = 5) -> list[City]:
        self.searches.append((name, lang))
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.cities


class StubCbr:
    def __init__(self) -> None:
        self.fail = False

    async def daily(self) -> Rates:
        if self.fail:
            raise UpstreamUnavailable(service="cbr")
        return Rates(date(2026, 9, 28), Rate(84.1975, -0.3118), Rate(96.6671, -0.8313))


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
