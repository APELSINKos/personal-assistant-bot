from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.errors import UpstreamUnavailable
from assistant.core.services import digest, money, notes, schedule

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)  # 08:00 Moscow
MIREA = (
    Path(__file__).resolve().parents[1] / "fixtures" / "schedule" / "mirea_ikbo_63_24.ics"
).read_bytes()


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


async def test_today_has_the_lessons_of_the_day(session, make_user) -> None:
    user = await make_user()
    data = await digest.today(session, user, Meteo(), Cbr(), NOW)
    assert (data.has_schedule, data.lessons, data.week_label) == (False, [], None)
    await schedule.connect_file(session, user, MIREA, "group.ics", NOW)
    await session.commit()
    wednesday = datetime(2026, 9, 30, 5, 0, tzinfo=UTC)  # 08:00 Moscow
    data = await digest.today(session, user, Meteo(), Cbr(), wednesday)
    assert data.has_schedule and data.week_label == "5 неделя"
    assert [(lesson.kind, lesson.title) for lesson in data.lessons] == [
        ("ПР", "Разработка баз данных")
    ]
    monday = await digest.today(session, user, Meteo(), Cbr(), NOW)
    assert monday.has_schedule and monday.lessons == []  # a connected day without lessons


async def test_today_has_the_money_of_today_yesterday_and_the_month(session, make_user) -> None:
    user = await make_user()
    now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)  # the 1st: yesterday is last month
    cafe = next(c for c in await money.categories(session, user) if c.preset == "cafe")
    for amount, day in ((25000, date(2026, 10, 1)), (40000, date(2026, 9, 30))):
        await money.add_entry(session, user, amount=amount, category_id=cafe.id, day=day, now=now)
    data = await digest.today(session, user, Meteo(), Cbr(), now)
    assert (data.spent_today, data.spent_yesterday, data.currency) == (25000, 40000, "RUB")
    assert data.money is not None and (data.money.first, data.money.spent) == (
        date(2026, 10, 1),
        25000,
    )
