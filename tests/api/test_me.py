from __future__ import annotations

import pytest

from assistant.core.clients.openmeteo import City

KAZAN = City(
    name="Казань",
    admin="Татарстан",
    country="Россия",
    lat=55.79,
    lon=49.12,
    timezone="Europe/Moscow",
)


async def test_language_setting_round_trip(client, auth) -> None:
    patched = await client.patch("/api/me", json={"language": "en"}, headers=auth())
    assert patched.status_code == 200
    assert patched.json()["language"] == "en" and patched.json()["language_setting"] == "en"
    reset = await client.patch("/api/me", json={"language": "auto"}, headers=auth(lang="ru"))
    assert reset.json()["language"] == "ru" and reset.json()["language_setting"] == "auto"


async def test_morning_settings(client, auth) -> None:
    response = await client.patch(
        "/api/me", json={"morning_enabled": False, "morning_time": "7:5"}, headers=auth()
    )
    assert response.json()["morning"] == {"enabled": False, "time": "07:05"}


@pytest.mark.parametrize(
    ("body", "field", "limit"),
    [
        ({"morning_time": "25:00"}, "time", None),
        ({"morning_time": "010:00"}, "morning_time", 5),
        ({"language": "de"}, "language", None),
        ({"colour": "red"}, "colour", None),
    ],
)
async def test_invalid_patch_is_422(client, auth, body, field, limit) -> None:
    response = await client.patch("/api/me", json=body, headers=auth())
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error" and response.json()["field"] == field
    if limit is not None:
        assert response.json()["limit"] == limit


async def test_set_city(client, auth) -> None:
    body = {"name": "Казань", "lat": 55.79, "lon": 49.12, "timezone": "Europe/Moscow"}
    response = await client.put("/api/me/city", json=body, headers=auth())
    assert response.status_code == 200 and response.json()["city"]["name"] == "Казань"
    again = await client.get("/api/me", headers=auth())
    assert again.json()["city"] == {
        "name": "Казань",
        "admin": None,
        "country": None,
        "lat": 55.79,
        "lon": 49.12,
        "timezone": "Europe/Moscow",
    }


@pytest.mark.parametrize(
    ("body", "limit"),
    [
        ({"name": "X", "lat": 10, "lon": 10, "timezone": "Mars/Olympus"}, None),
        ({"name": "X", "lat": 91, "lon": 10, "timezone": "Europe/Moscow"}, None),
        ({"name": "", "lat": 10, "lon": 10, "timezone": "Europe/Moscow"}, None),
        ({"name": "X" * 101, "lat": 10, "lon": 10, "timezone": "Europe/Moscow"}, 100),
    ],
)
async def test_invalid_city_is_422(client, auth, body, limit) -> None:
    response = await client.put("/api/me/city", json=body, headers=auth())
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    if limit is not None:
        assert response.json()["limit"] == limit


async def test_city_search_uses_user_language(client, auth, meteo) -> None:
    meteo.cities = [KAZAN]
    response = await client.get("/api/cities", params={"q": "Казань"}, headers=auth(lang="en"))
    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "Казань",
            "admin": "Татарстан",
            "country": "Россия",
            "lat": 55.79,
            "lon": 49.12,
            "timezone": "Europe/Moscow",
        }
    ]
    assert meteo.searches == [("Казань", "en")]


async def test_city_search_validation_and_outage(client, auth, meteo) -> None:
    short = await client.get("/api/cities", params={"q": "К"}, headers=auth())
    assert short.status_code == 422 and short.json()["limit"] == 2
    meteo.fail = True
    down = await client.get("/api/cities", params={"q": "Казань"}, headers=auth())
    assert down.status_code == 503 and down.json()["code"] == "upstream_unavailable"
