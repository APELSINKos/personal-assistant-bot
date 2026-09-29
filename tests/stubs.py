from __future__ import annotations

from datetime import date
from typing import Any

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.errors import UpstreamUnavailable


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
