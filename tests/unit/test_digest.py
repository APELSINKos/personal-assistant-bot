from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.errors import UpstreamUnavailable
from assistant.core.services import digest, notes

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)  # 08:00 Moscow


class Meteo:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def forecast(self, lat: float, lon: float) -> dict[str, object]:
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return {
            "current": {
                "time": "2026-09-28T08:00",
                "temperature_2m": 9,
                "weather_code": 1,
                "apparent_temperature": 7,
                "wind_speed_10m": 3,
                "precipitation": 0,
            },
            "daily": {"temperature_2m_max": [13], "temperature_2m_min": [6]},
        }


class Cbr:
    async def daily(self) -> Rates:
        return Rates(date(2026, 9, 28), Rate(84.2, -0.31), Rate(96.67, -0.83))


@pytest.mark.parametrize(
    ("hour", "part"),
    [
        (5, "morning"),
        (11, "morning"),
        (12, "day"),
        (17, "evening"),
        (22, "evening"),
        (23, "night"),
        (3, "night"),
    ],
)
def test_part_of_day(hour: int, part: str) -> None:
    assert digest.part_of_day(hour) == part


async def test_today_collects_everything(session, make_user) -> None:
    user = await make_user()
    await notes.create(session, user.id, "n")
    data = await digest.today(session, user, Meteo(), Cbr(), NOW)
    assert data.part_of_day == "morning" and data.local_now.hour == 8
    assert data.weather is not None and data.weather.temperature == 9
    assert data.rates is not None and data.notes_count == 1
    assert (data.habits_done, data.habits_total, data.best_streak) == (0, 0, None)


async def test_today_survives_upstream_failure(session, make_user) -> None:
    user = await make_user()
    data = await digest.today(session, user, Meteo(fail=True), Cbr(), NOW)
    assert data.weather is None and data.rates is not None
