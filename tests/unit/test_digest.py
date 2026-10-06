from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from assistant.core.clients.cbr import Rate, Rates
from assistant.core.errors import UpstreamUnavailable
from assistant.core.models import Lesson
from assistant.core.services import digest, money, notes, schedule
from tests.stubs import forecast_payload

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)  # 08:00 Moscow
MIREA = (
    Path(__file__).resolve().parents[1] / "fixtures" / "schedule" / "mirea_ikbo_63_24.ics"
).read_bytes()


class Meteo:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.requests = 0

    async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
        self.requests += 1
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return forecast_payload(NOW, temperature=9)


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
    await notes.create(session, user.id, "n", now=NOW)
    data = await digest.today(session, user, Meteo(), Cbr(), NOW)
    assert data.part_of_day == "morning" and data.local_now.hour == 8
    assert data.weather is not None and data.weather.temperature == 9
    assert data.rates is not None and data.notes_count == 1
    assert (data.habits_done, data.habits_total, data.best_streak) == (0, 0, None)


async def test_today_has_the_forecast_of_one_request(session, make_user) -> None:
    user = await make_user()
    meteo = Meteo()
    data = await digest.today(session, user, meteo, Cbr(), NOW)
    assert meteo.requests == 1
    assert data.forecast is not None and data.weather == data.forecast.now
    assert data.forecast.zone == "Europe/Moscow"
    # The days of the week ahead and its hours: «Завтра» and the way to the classes.
    assert [day.day for day in data.forecast.days][:2] == [date(2026, 9, 28), date(2026, 9, 29)]
    assert len(data.forecast.hours) == 7 * 24


async def test_today_has_the_first_three_pinned_notes(session, make_user) -> None:
    user = await make_user()
    assert (await digest.today(session, user, Meteo(), Cbr(), NOW)).pinned == []
    n0, n1, n2 = [await notes.create(session, user.id, f"n{i}", now=NOW) for i in range(3)]
    shopping = await notes.create(session, user.id, "Покупки", ["молоко", "хлеб"], now=NOW)
    await notes.set_item(session, user.id, shopping.id, shopping.items[0].id, True)
    # Pinned in an order that is neither the notes' order nor its reverse: the last pinned first.
    for minutes, view in enumerate([n1, shopping, n0, n2]):
        await notes.set_pinned(session, user.id, view.id, True, NOW + timedelta(minutes=minutes))
    data = await digest.today(session, user, Meteo(), Cbr(), NOW)
    assert [view.text for view in data.pinned] == ["n2", "n0", "Покупки"]
    assert (data.pinned[2].done, data.pinned[2].total) == (1, 2)
    assert data.notes_count == 4


async def test_today_survives_upstream_failure(session, make_user) -> None:
    user = await make_user()
    data = await digest.today(session, user, Meteo(fail=True), Cbr(), NOW)
    assert data.weather is None and data.forecast is None and data.rates is not None


async def test_today_survives_a_forecast_it_cannot_read(session, make_user, caplog) -> None:
    # Weather is not what «Мой день» is about: an answer the parser trips over is logged, without
    # anything of the answer, and the day comes without weather.
    class Garbled:
        async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
            return {"timezone": "Secret/Place", "current": []}

    user = await make_user()
    with caplog.at_level(logging.WARNING):
        data = await digest.today(session, user, Garbled(), Cbr(), NOW)
    assert data.weather is None and data.forecast is None and data.rates is not None
    assert "KeyError" in caplog.text and "Secret" not in caplog.text


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


async def test_tomorrow_comes_from_17_on_the_users_clock(session, make_user) -> None:
    # One rule for «Мой день» and «Сегодня»: the bot and the API both read it from here.
    user = await make_user()
    morning = await digest.today(session, user, Meteo(), Cbr(), NOW)  # 08:00 Moscow
    assert digest.tomorrow_weather(morning) is None
    evening = await digest.today(session, user, Meteo(), Cbr(), NOW + timedelta(hours=9))
    assert evening.local_now.hour == digest.TOMORROW_FROM == 17
    day = digest.tomorrow_weather(evening)
    assert day is not None and day.day == date(2026, 9, 29)
    assert digest.tomorrow_weather(replace(evening, forecast=None)) is None


async def test_the_way_to_classes_spans_the_first_start_and_the_last_end(
    session, make_user
) -> None:
    user = await make_user()
    data = await digest.today(session, user, Meteo(), Cbr(), NOW)  # 08:00 Moscow
    assert (digest.classes_span(data), digest.classes_weather(data)) == (None, None)
    late = Lesson(
        uid="b",
        starts_at=NOW + timedelta(hours=5),  # 13:00 Moscow
        ends_at=NOW + timedelta(hours=6, minutes=30),  # 14:30
        title="Физика",
    )
    early = Lesson(
        uid="a",
        starts_at=NOW + timedelta(hours=1),  # 09:00
        ends_at=NOW + timedelta(hours=2, minutes=30),
        title="Химия",
    )
    day = replace(data, lessons=[late, early])
    assert digest.classes_span(day) == (early.starts_at, late.ends_at)
    way = digest.classes_weather(day)
    # The whole day's answer on the user's clock, whatever the time now.
    assert way is not None
    assert (way.start, way.end) == (datetime(2026, 9, 28, 9, 0), datetime(2026, 9, 28, 14, 30))
    assert digest.classes_weather(replace(day, forecast=None)) is None


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
