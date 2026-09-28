"""Current weather and the 'smart' tips shown in the bot and the Mini App."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from assistant.core.clients.openmeteo import OpenMeteoClient

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
    tmin: float | None
    tmax: float | None
    tips: list[Tip]


def describe(code: int) -> tuple[str, str]:
    for first, last, emoji, key in _CODES:
        if first <= code <= last:
            return emoji, key
    return "🌡", "wmo-unknown"


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _first(values: object) -> float | None:
    return _num(values[0]) if isinstance(values, list) and values else None


def build_tips(data: Mapping[str, Any]) -> list[Tip]:
    current = data.get("current") or {}
    time_text = current.get("time")
    if not isinstance(time_text, str):
        return [Tip("tip-calm")]
    now = datetime.fromisoformat(time_text)
    temp = _num(current.get("temperature_2m"))
    feels = _num(current.get("apparent_temperature"))
    wind = _num(current.get("wind_speed_10m"))
    precip = _num(current.get("precipitation")) or 0.0
    kind = "snow" if temp is not None and temp <= 0 else "rain"
    tips: list[Tip] = []

    soon = False
    if precip >= 0.1:
        tips.append(Tip("tip-precip-now", {"kind": kind}))
        soon = True
    else:
        block = data.get("minutely_15") or {}
        steps = zip(block.get("time") or [], block.get("precipitation") or [], strict=False)
        for moment, amount in steps:
            value = _num(amount)
            if not isinstance(moment, str) or value is None:
                continue
            minutes = int((datetime.fromisoformat(moment) - now).total_seconds() // 60)
            if 0 < minutes <= 120 and value >= 0.1:
                tips.append(Tip("tip-precip-soon", {"kind": kind, "minutes": minutes}))
                soon = True
                break

    today: dict[int, tuple[float | None, float]] = {}
    hourly = data.get("hourly") or {}
    for moment, temperature, chance in zip(
        hourly.get("time") or [],
        hourly.get("temperature_2m") or [],
        hourly.get("precipitation_probability") or [],
        strict=False,
    ):
        if isinstance(moment, str):
            parsed = datetime.fromisoformat(moment)
            if parsed.date() == now.date():
                today[parsed.hour] = (_num(temperature), _num(chance) or 0.0)

    later = False
    if not soon:
        for hour in sorted(today):
            if hour > now.hour and today[hour][1] >= 60:
                tips.append(Tip("tip-precip-later", {"kind": kind, "hour": f"{hour:02d}:00"}))
                later = True
                break

    morning, evening = today.get(8, (None, 0.0))[0], today.get(18, (None, 0.0))[0]
    if morning is not None and evening is not None:
        if evening - morning >= 5:
            tips.append(Tip("tip-warmer-evening"))
        elif evening - morning <= -5:
            tips.append(Tip("tip-colder-evening"))
    if wind is not None and wind >= 10:
        tips.append(Tip("tip-wind"))
    if feels is not None and feels <= -15:
        tips.append(Tip("tip-frost"))
    if feels is not None and feels >= 30:
        tips.append(Tip("tip-heat"))
    tmax = _first((data.get("daily") or {}).get("temperature_2m_max"))
    calm_wind = wind is not None and wind < 7
    if not (soon or later) and tmax is not None and 12 <= tmax <= 28 and calm_wind:
        tips.append(Tip("tip-bike"))
    return tips or [Tip("tip-calm")]


async def current(client: OpenMeteoClient, city: str, lat: float, lon: float) -> WeatherNow:
    data = await client.forecast(lat, lon)
    now = data.get("current") or {}
    daily = data.get("daily") or {}
    code = _num(now.get("weather_code"))
    return WeatherNow(
        city=city,
        temperature=_num(now.get("temperature_2m")),
        feels_like=_num(now.get("apparent_temperature")),
        wind=_num(now.get("wind_speed_10m")),
        code=int(code) if code is not None else -1,
        tmin=_first(daily.get("temperature_2m_min")),
        tmax=_first(daily.get("temperature_2m_max")),
        tips=build_tips(data),
    )
