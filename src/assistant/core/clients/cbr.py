"""Official Central Bank of Russia rates: the day's rates of every currency (cbr-xml-daily.ru
mirror, JSON) and a currency's rates over a period (cbr.ru XML_dynamic).

An exchange takes `deadline` seconds in all. One that fails in the network (no answer in time, a
connection refused or dropped) pauses that host for a minute: a mirror that hangs would otherwise
make every caller wait it out in turn, the morning digests of a window among them. An answer that
came, an error status or a body that cannot be read, pauses nothing: it came at once."""

from __future__ import annotations

import asyncio
import math
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx

from assistant.core.errors import UpstreamUnavailable

RATES_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
HISTORY_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"
HISTORY_LIMIT = 256 * 1024  # bytes; a year of one currency is about 30 KB
HISTORY_TTL = 6 * 3600.0  # the rates change once a day
PAUSE = 60.0  # seconds without requests to a host after a failure in the network


@dataclass(frozen=True)
class Rate:
    value: float  # roubles for one unit
    change: float


@dataclass(frozen=True)
class Rates:
    day: date
    usd: Rate
    eur: Rate
    currencies: Mapping[str, Rate] = field(default_factory=dict)  # every currency by ISO code
    ids: Mapping[str, str] = field(default_factory=dict)  # ISO code → the bank's id, R01235


@dataclass(frozen=True)
class Point:
    day: date
    value: float  # roubles for one unit


def _rate(item: object) -> Rate:
    if not isinstance(item, dict):
        raise ValueError("bad currency item")
    nominal = float(item["Nominal"])
    value = float(item["Value"]) / nominal
    previous = float(item["Previous"]) / nominal
    if not (math.isfinite(value) and math.isfinite(previous)) or value <= 0:
        raise ValueError("bad rate")
    return Rate(value, value - previous)


def _points(body: bytes) -> list[Point]:
    """XML_dynamic's answer: windows-1251, values with a decimal comma, one Record a day."""
    if len(body) > HISTORY_LIMIT or b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise ValueError("unexpected answer")
    root = ET.fromstring(body.decode("cp1251").split("?>", 1)[-1])
    points = []
    for record in root.iter("Record"):
        day = datetime.strptime(record.get("Date", ""), "%d.%m.%Y").date()
        value = float((record.findtext("VunitRate") or "").replace(",", "."))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("bad rate")
        points.append(Point(day, value))
    if not points:  # the bank quotes the currency today: no day at all is a fault, tried again
        raise ValueError("no records")
    return sorted(points, key=lambda point: point.day)


class CbrClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        ttl: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
        *,
        deadline: float = 10.0,
    ) -> None:
        self._http = http
        self._ttl = ttl
        self._clock = clock
        self._deadline = deadline
        self._cached: tuple[float, Rates] | None = None
        self._history: dict[tuple[str, date, int], tuple[float, list[Point]]] = {}
        # The mirror and cbr.ru are paused until these moments of `clock`.
        self._daily_resume_at = -math.inf
        self._history_resume_at = -math.inf

    async def daily(self) -> Rates:
        if self._cached and self._clock() - self._cached[0] < self._ttl:
            return self._cached[1]
        if self._clock() < self._daily_resume_at:
            raise UpstreamUnavailable(service="cbr")
        try:
            async with asyncio.timeout(self._deadline):
                response = await self._http.get(RATES_URL)
            response.raise_for_status()
            data = response.json()
            currencies: dict[str, Rate] = {}
            ids: dict[str, str] = {}
            for code, item in data["Valute"].items():
                try:
                    currencies[code] = _rate(item)
                except (ValueError, KeyError, TypeError, ZeroDivisionError):
                    continue  # one odd currency does not hide the others
                if isinstance(item.get("ID"), str):
                    ids[code] = item["ID"]
            rates = Rates(
                day=datetime.fromisoformat(data["Date"]).date(),
                usd=currencies["USD"],
                eur=currencies["EUR"],
                currencies=currencies,
                ids=ids,
            )
        except (TimeoutError, httpx.TransportError) as error:
            self._daily_resume_at = self._clock() + PAUSE
            raise UpstreamUnavailable(service="cbr") from error
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise UpstreamUnavailable(service="cbr") from error
        self._cached = (self._clock(), rates)
        return rates

    async def history(self, code: str, days: int = 30) -> list[Point]:
        """The currency's rates over the last `days` days up to the day of the latest rates;
        the bank sets rates on working days only. LookupError for a currency it does not have."""
        rates = await self.daily()
        if code not in rates.ids:
            raise LookupError(code)
        key = (code, rates.day, days)
        cached = self._history.get(key)
        if cached and self._clock() - cached[0] < HISTORY_TTL:
            return cached[1]
        if self._clock() < self._history_resume_at:
            raise UpstreamUnavailable(service="cbr")
        params = {
            "date_req1": (rates.day - timedelta(days=days)).strftime("%d/%m/%Y"),
            "date_req2": rates.day.strftime("%d/%m/%Y"),
            "VAL_NM_RQ": rates.ids[code],
        }
        try:
            async with asyncio.timeout(self._deadline):
                response = await self._http.get(HISTORY_URL, params=params)
            response.raise_for_status()
            points = _points(response.content)
        except (TimeoutError, httpx.TransportError) as error:
            self._history_resume_at = self._clock() + PAUSE
            raise UpstreamUnavailable(service="cbr") from error
        except (httpx.HTTPError, ValueError, ET.ParseError, UnicodeDecodeError) as error:
            raise UpstreamUnavailable(service="cbr") from error
        # Only the latest day's histories are worth keeping.
        self._history = {k: v for k, v in self._history.items() if k[1] == rates.day}
        self._history[key] = (self._clock(), points)
        return points
