from __future__ import annotations

from typing import Any

from assistant.core.services.weather import Tip, build_tips, describe


def forecast(
    *,
    now: str = "2026-09-28T10:00",
    temp: float | None = 10,
    feels: float | None = 9,
    wind: float | None = 2,
    precip: float | None = 0,
    minutely: list[float] | None = None,
    morning: float = 8,
    evening: float = 10,
    later_chance: int = 0,
    tmax: float | None = 13,
) -> dict[str, Any]:
    hours = [f"2026-09-28T{h:02d}:00" for h in range(24)]
    temps = [morning if h == 8 else evening if h == 18 else 9 for h in range(24)]
    chances = [later_chance if h == 17 else 0 for h in range(24)]
    data: dict[str, Any] = {
        "current": {
            "time": now,
            "temperature_2m": temp,
            "apparent_temperature": feels,
            "wind_speed_10m": wind,
            "precipitation": precip,
            "weather_code": 1,
        },
        "hourly": {"time": hours, "temperature_2m": temps, "precipitation_probability": chances},
        "daily": {"temperature_2m_max": [tmax], "temperature_2m_min": [5]},
    }
    if minutely is not None:
        moments = [
            f"2026-09-28T{10 + (i * 15) // 60:02d}:{(i * 15) % 60:02d}"
            for i in range(len(minutely))
        ]
        data["minutely_15"] = {"time": moments, "precipitation": minutely}
    return data


def keys(tips: list[Tip]) -> list[str]:
    return [tip.key for tip in tips]


def test_rain_in_45_minutes() -> None:
    tips = build_tips(forecast(minutely=[0, 0, 0, 0.6]))
    assert tips[0] == Tip("tip-precip-soon", {"kind": "rain", "minutes": 45})


def test_snow_now_with_frost_and_wind() -> None:
    tips = build_tips(forecast(temp=-18, feels=-25, precip=0.4, wind=12))
    assert keys(tips)[:1] == ["tip-precip-now"] and tips[0].params == {"kind": "snow"}
    assert {"tip-wind", "tip-frost"} <= set(keys(tips))


def test_snow_later_uses_snow_kind() -> None:
    tips = build_tips(forecast(temp=-2, later_chance=80))
    assert tips[0] == Tip("tip-precip-later", {"kind": "snow", "hour": "17:00"})


def test_missing_minutely_block_is_fine() -> None:
    assert "tip-precip-soon" not in keys(build_tips(forecast(minutely=None)))


def test_none_values_do_not_crash() -> None:
    tips = build_tips(forecast(temp=None, feels=None, wind=None, precip=None, tmax=None))
    assert tips  # at least the calm tip or evening tip


def test_bike_day_and_warmer_evening() -> None:
    assert keys(build_tips(forecast(morning=6, evening=14, tmax=16))) == [
        "tip-warmer-evening",
        "tip-bike",
    ]


def test_calm_when_nothing_special() -> None:
    assert keys(build_tips(forecast(tmax=5))) == ["tip-calm"]


def test_missing_current_block() -> None:
    assert keys(build_tips({})) == ["tip-calm"]


def test_describe_codes() -> None:
    assert describe(0) == ("☀️", "wmo-clear")
    assert describe(63) == ("🌧", "wmo-rain")
    assert describe(1234) == ("🌡", "wmo-unknown")
