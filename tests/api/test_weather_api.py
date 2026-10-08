from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from tests.stubs import forecast_payload

TULA = {
    "name": "Тула",
    "admin": "Тульская область",
    "country": "Россия",
    "lat": 54.19,
    "lon": 37.62,
    "timezone": "Europe/Moscow",
    "geo_id": 480562,
}
VLADIVOSTOK = {
    **TULA,
    "name": "Владивосток",
    "admin": "Приморский край",
    "lat": 43.11,
    "lon": 131.87,
    "timezone": "Asia/Vladivostok",
    "geo_id": 2013348,
}


def record_places(meteo, monkeypatch) -> list[tuple[float, float]]:
    """The coordinates the API asks the forecast for."""
    places: list[tuple[float, float]] = []
    forecast = meteo.forecast

    async def recorded(lat: float, lon: float, **options: Any) -> dict[str, Any]:
        places.append((lat, lon))
        return await forecast(lat, lon, **options)

    monkeypatch.setattr(meteo, "forecast", recorded)
    return places


async def test_the_forecast_of_the_home_city(client, auth, meteo, monkeypatch) -> None:
    # The stub forecast was asked for at 10:00 in Moscow, the app asks at 15:00 (conftest NOW).
    places = record_places(meteo, monkeypatch)
    response = await client.get("/api/weather", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert places == [(55.75204, 37.61781)]  # the home city of a new user
    assert meteo.user_ids == [1]  # whose budget it spent
    assert body["city"] == {"id": 0, "name": "Москва", "home": True}
    assert body["now"] == {
        "temperature": 9.6,
        "feels_like": 7.2,
        "wind": 3.4,
        "gusts": 6.1,
        "humidity": 71,
        "is_day": True,
        "emoji": "🌤",
        "description": "малооблачно",
        "precip_chance": 0,
    }
    assert body["tips"] == ["🚲 Сегодня хороший день для велосипеда"]
    # The 23 hours after 15:00: the evening, the night with the moon, the next day to 14:00.
    hours = body["hours"]
    assert len(hours) == 23
    assert hours[0] == {
        "time": "16:00",
        "emoji": "🌤",
        "description": "малооблачно",
        "temperature": 13.0,
        "precip_chance": 0,
    }
    assert (hours[3]["time"], hours[3]["emoji"], hours[3]["temperature"]) == ("19:00", "🌙", 10.6)
    assert (hours[-1]["time"], hours[-1]["emoji"], hours[-1]["temperature"]) == ("14:00", "🌤", 13.1)
    assert body["days"][0] == {
        "date": "2026-09-28",
        "emoji": "🌤",
        "description": "малооблачно",
        "tmin": 5.8,
        "tmax": 13.2,
        "precip_chance": 0,
    }
    assert [day["date"] for day in body["days"]] == [
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]
    assert (body["sunrise"], body["sunset"], body["polar"]) == ("06:40", "18:40", None)


async def test_the_forecast_speaks_the_users_language(client, auth) -> None:
    body = (await client.get("/api/weather", headers=auth(lang="en"))).json()
    assert body["now"]["description"] == "partly cloudy"
    assert body["tips"] == ["🚲 A great day for a bike ride"]
    assert body["hours"][0]["description"] == body["days"][0]["description"] == "partly cloudy"


async def test_now_has_the_chance_of_the_hour_going_on(client, auth, clock, meteo) -> None:
    data = forecast_payload()
    chances = data["hourly"]["precipitation_probability"]
    chances[15], chances[16] = 90, 40  # 14:00–15:00 and 15:00–16:00
    meteo.forecast_data = data
    clock[0] = datetime(2026, 9, 28, 12, 20, tzinfo=UTC)  # 15:20 in Moscow
    body = (await client.get("/api/weather", headers=auth())).json()
    assert body["now"]["precip_chance"] == 40
    assert (body["hours"][0]["time"], body["hours"][0]["precip_chance"]) == ("16:00", 40)
    chances[16] = None
    body = (await client.get("/api/weather", headers=auth())).json()
    assert body["now"]["precip_chance"] is None and body["hours"][0]["precip_chance"] is None


async def test_a_missing_hour_is_left_out(client, auth, meteo) -> None:
    data = forecast_payload()
    data["hourly"]["temperature_2m"][17] = None
    meteo.forecast_data = data
    hours = (await client.get("/api/weather", headers=auth())).json()["hours"]
    times = [hour["time"] for hour in hours]
    assert times[:3] == ["16:00", "18:00", "19:00"]
    assert len(times) == 23 and times[-1] == "15:00"


async def test_the_last_day_has_fewer_hours(client, auth, clock) -> None:
    clock[0] = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)  # 15:00 of the forecast's last day
    body = (await client.get("/api/weather", headers=auth(signed_at=clock[0]))).json()
    assert [hour["time"] for hour in body["hours"]] == [f"{hour}:00" for hour in range(16, 24)]
    assert [day["date"] for day in body["days"]] == ["2026-10-04"]


async def test_just_after_midnight_the_week_has_six_days(client, auth, clock, meteo) -> None:
    data = forecast_payload()
    daily = data["daily"]
    # The forecast's first day, the 28th, is over: a polar night there; the 29th has its own sun.
    daily["sunrise"][0] = daily["sunset"][0] = daily["time"][0]
    daily["sunrise"][1] = daily["time"][1] + 6 * 3600 + 42 * 60
    daily["sunset"][1] = daily["time"][1] + 18 * 3600 + 37 * 60
    meteo.forecast_data = data
    clock[0] = datetime(2026, 9, 28, 21, 30, tzinfo=UTC)  # 00:30 of the 29th in Moscow
    body = (await client.get("/api/weather", headers=auth(signed_at=clock[0]))).json()
    assert body["days"][0]["date"] == "2026-09-29" and len(body["days"]) == 6
    assert body["hours"][0]["time"] == "01:00" and body["hours"][-1]["time"] == "23:00"
    # The sun of days[0], the city's today, not of the forecast's first day.
    assert (body["sunrise"], body["sunset"], body["polar"]) == ("06:42", "18:37", None)


async def test_times_and_dates_are_on_the_citys_clock(client, auth, clock, meteo) -> None:
    city = (await client.post("/api/me/cities", json=VLADIVOSTOK, headers=auth())).json()
    meteo.forecast_data = forecast_payload(zone="Asia/Vladivostok")
    # 21:30 of the 28th for the user in Moscow, 04:30 of the 29th in Vladivostok.
    clock[0] = datetime(2026, 9, 28, 18, 30, tzinfo=UTC)
    path = f"/api/weather?city={city['id']}"
    body = (await client.get(path, headers=auth(signed_at=clock[0]))).json()
    assert body["days"][0]["date"] == "2026-09-29" and len(body["days"]) == 6
    assert body["hours"][0]["time"] == "05:00"
    assert (body["sunrise"], body["sunset"]) == ("06:40", "18:40")


@pytest.mark.parametrize(("sunset_after", "polar"), [(0, "night"), (86_400, "day")])
async def test_a_polar_night_or_day_has_no_sun_times(
    client, auth, meteo, sunset_after, polar
) -> None:
    data = forecast_payload()
    # Open-Meteo gives midnights then: a sunrise equal to the sunset, or a day apart.
    midnight = data["daily"]["time"][0]
    data["daily"]["sunrise"][0], data["daily"]["sunset"][0] = midnight, midnight + sunset_after
    meteo.forecast_data = data
    body = (await client.get("/api/weather", headers=auth())).json()
    assert (body["sunrise"], body["sunset"], body["polar"]) == (None, None, polar)


async def test_an_extra_city(client, auth, meteo, monkeypatch) -> None:
    city = (await client.post("/api/me/cities", json=TULA, headers=auth())).json()
    places = record_places(meteo, monkeypatch)
    response = await client.get(f"/api/weather?city={city['id']}", headers=auth())
    assert response.status_code == 200
    assert response.json()["city"] == {"id": city["id"], "name": "Тула", "home": False}
    assert places == [(54.19, 37.62)]
    home = (await client.get("/api/weather?city=0", headers=auth())).json()
    assert home["city"] == {"id": 0, "name": "Москва", "home": True}


async def test_a_foreign_or_deleted_city_is_404(client, auth) -> None:
    foreign = (await client.post("/api/me/cities", json=TULA, headers=auth(2))).json()
    mine = (await client.post("/api/me/cities", json=TULA, headers=auth(1))).json()
    await client.delete(f"/api/me/cities/{mine['id']}", headers=auth(1))
    for city_id in (foreign["id"], mine["id"], 2**63 - 1):
        response = await client.get(f"/api/weather?city={city_id}", headers=auth(1))
        assert response.status_code == 404
        assert (response.json()["code"], response.json()["entity"]) == ("not_found", "city")


@pytest.mark.parametrize("city", ["-1", str(2**63), "1.5", "home"])
async def test_a_city_that_is_not_an_id_is_422(client, auth, city) -> None:
    response = await client.get(f"/api/weather?city={city}", headers=auth())
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == ("validation_error", "city")


async def test_the_forecast_is_503_when_open_meteo_is_down(client, auth, meteo) -> None:
    city = (await client.post("/api/me/cities", json=TULA, headers=auth())).json()
    meteo.fail = True
    for path in ("/api/weather", f"/api/weather?city={city['id']}"):
        response = await client.get(path, headers=auth())
        assert response.status_code == 503
        assert response.json()["code"] == "upstream_unavailable"
