from __future__ import annotations

from datetime import UTC, date, datetime

from assistant.core.models import Reminder, ReminderStatus
from assistant.core.services import habits, notes
from tests.stubs import forecast_payload


async def test_today_collects_everything(client, auth, session, make_user) -> None:
    user = await make_user(id=1)
    await notes.create(session, 1, "молоко")
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


async def test_weather_and_rates(client, auth) -> None:
    weather = (await client.get("/api/weather", headers=auth())).json()
    assert weather["tmin"] == 5.8 and weather["tmax"] == 13.2 and weather["wind"] == 3.4
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
