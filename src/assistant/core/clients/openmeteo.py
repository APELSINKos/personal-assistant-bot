"""Open-Meteo forecast and geocoding (no API key)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from assistant.core.errors import UpstreamUnavailable

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_PARAMS = {
    "timezone": "auto",
    "forecast_days": 2,
    "wind_speed_unit": "ms",
    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
    "minutely_15": "precipitation",
    "hourly": "temperature_2m,precipitation_probability",
    "daily": "temperature_2m_max,temperature_2m_min",
}


@dataclass(frozen=True)
class City:
    name: str
    admin: str | None
    country: str | None
    lat: float
    lon: float
    timezone: str


class OpenMeteoClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        ttl: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise UpstreamUnavailable(service="open-meteo") from error
        if not isinstance(data, dict):
            raise UpstreamUnavailable(service="open-meteo")
        return data

    async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
        key = (round(lat, 2), round(lon, 2))
        cached = self._cache.get(key)
        if cached and self._clock() - cached[0] < self._ttl:
            return cached[1]
        params = {"latitude": lat, "longitude": lon, **_FORECAST_PARAMS}
        data = await self._get_json(FORECAST_URL, params)
        self._cache[key] = (self._clock(), data)
        return data

    async def search(self, name: str, lang: str, count: int = 5) -> list[City]:
        data = await self._get_json(GEOCODING_URL, {"name": name, "count": count, "language": lang})
        cities: list[City] = []
        for item in data.get("results") or []:
            try:
                cities.append(
                    City(
                        name=str(item["name"]),
                        admin=item.get("admin1"),
                        country=item.get("country"),
                        lat=float(item["latitude"]),
                        lon=float(item["longitude"]),
                        timezone=str(item.get("timezone") or "UTC"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return cities
