from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from assistant.core.models import Lesson, Reminder, ReminderStatus, ScheduleKind, ScheduleSource
from assistant.core.services import habits, notes
from tests.api.conftest import NOW
from tests.stubs import forecast_payload

MOSCOW = ZoneInfo("Europe/Moscow")


def moscow(hour: int, minute: int = 0, day: int = 28) -> datetime:
    """A moment of September 2026 by Moscow's clock, the zone of the stub forecast."""
    return datetime(2026, 9, day, hour, minute, tzinfo=MOSCOW).astimezone(UTC)


async def add_lessons(session, user_id: int, *spans: tuple[datetime, datetime]) -> None:
    """A timetable with these lessons."""
    session.add(
        ScheduleSource(
            user_id=user_id,
            kind=ScheduleKind.FILE,
            title="Пары",
            body=b"",
            fetched_at=NOW,
            ok_at=NOW,
            next_refresh_at=NOW + timedelta(days=1),
        )
    )
    session.add_all(
        Lesson(user_id=user_id, uid=f"lesson-{number}", starts_at=start, ends_at=end, title="Пара")
        for number, (start, end) in enumerate(spans)
    )
    await session.commit()


async def test_today_collects_everything(client, auth, session, make_user) -> None:
    user = await make_user(id=1)
    await notes.create(session, 1, "молоко", now=NOW)
    habit = await habits.create(session, user, "Спорт", now=datetime(2026, 9, 27, 9, tzinfo=UTC))
    await habits.set_mark(
        session, user, habit.id, date(2026, 9, 27), True, now=datetime(2026, 9, 28, 12, tzinfo=UTC)
    )
    due = datetime(2026, 9, 28, 16, 30, tzinfo=UTC)  # 19:30 in Moscow, later the same day
    session.add(
        Reminder(
            user_id=1, text="созвон", due_at=due, next_attempt_at=due, status=ReminderStatus.PENDING
        )
    )
    await session.commit()

    response = await client.get("/api/today", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-09-28" and body["part_of_day"] == "day"
    assert body["weather"]["city"] == "Москва" and body["weather"]["temperature"] == 9.6
    assert body["weather"]["description"] == "малооблачно" and body["weather"]["emoji"] == "🌤"
    assert body["weather"]["tips"] == ["🚲 Сегодня хороший день для велосипеда"]
    assert body["reminders_today"] == [
        {
            "id": body["reminders_today"][0]["id"],
            "text": "созвон",
            "time": "19:30",
            "due_at": "2026-09-28T16:30:00Z",
        }
    ]
    assert body["habits"]["done"] == 0 and body["habits"]["total"] == 1
    item = body["habits"]["items"][0]
    assert item["name"] == "Спорт" and item["streak"] == 1 and item["done_today"] is None
    assert item["last_days"][-2:] == [True, None] and len(item["last_days"]) == 9
    assert body["notes_count"] == 1
    assert body["rates"] == {
        "date": "2026-09-28",
        "usd": {"value": 84.1975, "change": -0.3118},
        "eur": {"value": 96.6671, "change": -0.8313},
    }
    assert body["best_streak"] == {"name": "Спорт", "count": 1, "unit": "days"}
    # 15:00, no timetable, no pinned notes.
    assert (body["tomorrow"], body["classes_weather"], body["pinned_notes"]) == (None, None, [])


async def test_today_speaks_english(client, auth) -> None:
    body = (await client.get("/api/today", headers=auth(lang="en"))).json()
    assert body["weather"]["description"] == "partly cloudy"
    assert body["weather"]["tips"] == ["🚲 A great day for a bike ride"]


async def test_the_weather_card_shows_the_moon_at_night(client, auth, meteo) -> None:
    meteo.forecast_data = forecast_payload(is_day=0)
    weather = (await client.get("/api/today", headers=auth())).json()["weather"]
    assert (weather["emoji"], weather["description"]) == ("🌙", "малооблачно")


async def test_today_survives_upstream_failures(client, auth, meteo, cbr) -> None:
    meteo.fail = cbr.fail = True
    response = await client.get("/api/today", headers=auth())
    assert response.status_code == 200
    assert response.json()["weather"] is None and response.json()["rates"] is None


async def test_today_spends_the_weather_budget_of_its_user(client, auth, meteo) -> None:
    assert (await client.get("/api/today", headers=auth(7))).status_code == 200
    assert meteo.user_ids == [7]


async def test_weather_and_rates(client, auth) -> None:
    weather = (await client.get("/api/weather", headers=auth())).json()
    today = weather["days"][0]
    assert (today["tmin"], today["tmax"], weather["now"]["wind"]) == (5.8, 13.2, 3.4)
    rates = (await client.get("/api/rates", headers=auth())).json()
    assert rates["usd"]["value"] == 84.1975


async def test_weather_503_when_upstream_down(client, auth, meteo, cbr) -> None:
    meteo.fail = cbr.fail = True
    for path in ("/api/weather", "/api/rates"):
        response = await client.get(path, headers=auth())
        assert response.status_code == 503
        assert response.json()["code"] == "upstream_unavailable"
        assert response.headers["content-type"].startswith("application/problem+json")


async def test_today_lists_todays_firing_of_a_repeat(client, auth) -> None:
    rule = {"repeat": "daily", "time_local": "21:00"}
    created = await client.post(
        "/api/reminders", json={"text": "таблетки", "rule": rule}, headers=auth()
    )
    assert created.status_code == 201
    body = (await client.get("/api/today", headers=auth())).json()
    assert [(r["text"], r["time"]) for r in body["reminders_today"]] == [("таблетки", "21:00")]


@pytest.mark.parametrize(
    ("moment", "shown"),
    [
        (moscow(16, 59), False),
        (moscow(17, 0), True),
        (moscow(23, 59), True),
        (moscow(0, 0, day=29), False),
    ],
)
async def test_tomorrow_comes_in_the_evening(client, auth, clock, meteo, moment, shown) -> None:
    data = forecast_payload()
    daily = data["daily"]
    daily["weather_code"][1], daily["precipitation_probability_max"][1] = 61, 80
    daily["temperature_2m_min"][1], daily["temperature_2m_max"][1] = 1.6, 7.2
    meteo.forecast_data = data
    clock[0] = moment
    body = (await client.get("/api/today", headers=auth(signed_at=moment))).json()
    tomorrow = {
        "date": "2026-09-29",
        "emoji": "🌧",
        "description": "дождь",
        "tmin": 1.6,
        "tmax": 7.2,
        "precip_chance": 80,
    }
    assert body["tomorrow"] == (tomorrow if shown else None)


async def test_tomorrow_follows_the_users_clock(client, auth, clock, make_user) -> None:
    await make_user(id=1, tz="Europe/Samara")  # an hour ahead of the forecast's Moscow
    clock[0] = moscow(16, 30)
    body = (await client.get("/api/today", headers=auth(signed_at=clock[0]))).json()
    assert body["tomorrow"]["date"] == "2026-09-29"


async def test_no_tomorrow_without_its_forecast(client, auth, clock, meteo) -> None:
    clock[0] = moscow(18)
    meteo.forecast_data = forecast_payload(days=1)
    body = (await client.get("/api/today", headers=auth(signed_at=clock[0]))).json()
    assert body["weather"] is not None and body["tomorrow"] is None
    meteo.fail = True
    body = (await client.get("/api/today", headers=auth(signed_at=clock[0]))).json()
    assert body["weather"] is None and body["tomorrow"] is None


async def test_the_weather_of_the_way_to_classes_and_back(
    client, auth, clock, meteo, session, make_user
) -> None:
    await make_user(id=1)
    await add_lessons(
        session,
        1,
        (moscow(10, 40), moscow(12, 10)),
        (moscow(9, 0), moscow(10, 30)),
        (moscow(14, 50), moscow(16, 20)),
    )
    data = forecast_payload()
    chances = data["hourly"]["precipitation_probability"]
    chances[9], chances[17] = 70, 29  # the way there (08:00–09:00) and back (16:20–17:00)
    meteo.forecast_data = data
    expected = {
        "start": "09:00",
        "start_temp": 8.8,
        "start_chance": 70,
        "end": "16:20",
        "end_temp": 13.0,  # the hour of 16:00
        "end_chance": None,  # under 30 %
    }
    # The whole day's, whatever the time: the app hides what is over.
    for moment in (moscow(7), moscow(12), moscow(18)):
        clock[0] = moment
        body = (await client.get("/api/today", headers=auth(signed_at=moment))).json()
        assert body["classes_weather"] == expected
    chances[17] = 30
    body = (await client.get("/api/today", headers=auth(signed_at=clock[0]))).json()
    assert body["classes_weather"] == {**expected, "end_chance": 30}


async def test_the_way_back_is_after_the_class_that_ends_last(
    client, auth, meteo, session, make_user
) -> None:
    await make_user(id=1)
    # A lab all day and a short lecture inside it: the lecture starts last, the lab ends last.
    await add_lessons(
        session,
        1,
        (moscow(9, 0), moscow(17, 30)),
        (moscow(14, 50), moscow(16, 20)),
    )
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][18] = 60  # the way back (17:30–18:00)
    meteo.forecast_data = data
    body = (await client.get("/api/today", headers=auth())).json()
    assert body["classes_weather"] == {
        "start": "09:00",
        "start_temp": 8.8,
        "start_chance": None,
        "end": "17:30",
        "end_temp": 12.4,  # the hour of 17:00
        "end_chance": 60,
    }


async def test_classes_weather_needs_the_hour_of_the_end(
    client, auth, meteo, session, make_user
) -> None:
    await make_user(id=1)
    await add_lessons(session, 1, (moscow(9, 0), moscow(16, 20)))
    data = forecast_payload()
    temperatures = data["hourly"]["temperature_2m"]
    temperatures[9] = None  # no forecast for the way there: no part about it
    meteo.forecast_data = data
    body = (await client.get("/api/today", headers=auth())).json()
    assert body["classes_weather"] == {
        "start": "09:00",
        "start_temp": None,
        "start_chance": None,
        "end": "16:20",
        "end_temp": 13.0,
        "end_chance": None,
    }
    temperatures[16] = None  # nor for the way back: no line at all
    body = (await client.get("/api/today", headers=auth())).json()
    assert body["classes_weather"] is None
    meteo.fail = True
    body = (await client.get("/api/today", headers=auth())).json()
    assert body["lessons"] != [] and body["classes_weather"] is None


async def test_classes_times_are_on_the_users_clock(client, auth, session, make_user) -> None:
    await make_user(id=1, tz="Europe/Samara")
    await add_lessons(session, 1, (moscow(9, 0), moscow(16, 20)))
    weather = (await client.get("/api/today", headers=auth())).json()["classes_weather"]
    # The hours of the forecast are Moscow's 09:00 and 16:00; the user reads them an hour on.
    assert (weather["start"], weather["start_temp"]) == ("10:00", 8.8)
    assert (weather["end"], weather["end_temp"]) == ("17:20", 13.0)


async def test_today_has_the_first_three_pinned_notes(client, auth, clock) -> None:
    async def note(text: str, **fields: object) -> dict:
        created = await client.post("/api/notes", json={"text": text, **fields}, headers=auth())
        return created.json()

    await note("не закреплена")
    password = await note("Пароль от wifi: hunter2")
    shopping = await note("Покупки", items=["молоко", "хлеб", "сыр"])
    plan = await note("План на неделю\n" + " ".join(["пункт"] * 60))  # 374 characters
    ideas = await note("Идеи")
    for minutes, pinned in enumerate((password, shopping, plan, ideas), start=1):
        clock[0] = NOW + timedelta(minutes=minutes)
        await client.patch(f"/api/notes/{pinned['id']}", json={"pinned": True}, headers=auth())
    milk = shopping["items"][0]["id"]
    path = f"/api/notes/{shopping['id']}/items/{milk}"
    await client.patch(path, json={"done": True}, headers=auth())
    body = (await client.get("/api/today", headers=auth())).json()
    # The last pinned first, the text whole; a note without items has 0 of 0.
    assert body["pinned_notes"] == [
        {"id": ideas["id"], "text": "Идеи", "done": 0, "total": 0},
        {"id": plan["id"], "text": plan["text"], "done": 0, "total": 0},
        {"id": shopping["id"], "text": "Покупки", "done": 1, "total": 3},
    ]
    assert len(plan["text"]) == 374 and body["notes_count"] == 5
