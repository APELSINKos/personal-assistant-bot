"""Official Central Bank of Russia daily rates (cbr-xml-daily.ru mirror, JSON)."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from assistant.core.errors import UpstreamUnavailable

RATES_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


@dataclass(frozen=True)
class Rate:
    value: float
    change: float


@dataclass(frozen=True)
class Rates:
    day: date
    usd: Rate
    eur: Rate


def _rate(item: object) -> Rate:
    if not isinstance(item, dict):
        raise ValueError("bad currency item")
    nominal = float(item["Nominal"])
    value = float(item["Value"]) / nominal
    previous = float(item["Previous"]) / nominal
    if not (math.isfinite(value) and math.isfinite(previous)) or value <= 0:
        raise ValueError("bad rate")
    return Rate(value, value - previous)


class CbrClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        ttl: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._ttl = ttl
        self._clock = clock
        self._cached: tuple[float, Rates] | None = None

    async def daily(self) -> Rates:
        if self._cached and self._clock() - self._cached[0] < self._ttl:
            return self._cached[1]
        try:
            response = await self._http.get(RATES_URL)
            response.raise_for_status()
            data = response.json()
            valute = data["Valute"]
            rates = Rates(
                day=datetime.fromisoformat(data["Date"]).date(),
                usd=_rate(valute["USD"]),
                eur=_rate(valute["EUR"]),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
            raise UpstreamUnavailable(service="cbr") from error
        self._cached = (self._clock(), rates)
        return rates
