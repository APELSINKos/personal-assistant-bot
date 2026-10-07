from __future__ import annotations

import pytest

from assistant.core.clients.openmeteo import City


def place(
    name: str, admin: str, lat: float, lon: float, zone: str, geo_id: int
) -> dict[str, object]:
    """A place as GET /cities gives it and POST /me/cities takes it."""
    return {
        "name": name,
        "admin": admin,
        "country": "Россия",
        "lat": lat,
        "lon": lon,
        "timezone": zone,
        "geo_id": geo_id,
    }


TULA = place("Тула", "Тульская область", 54.19, 37.62, "Europe/Moscow", 480562)
SOCHI = place("Сочи", "Краснодарский край", 43.6, 39.73, "Europe/Moscow", 491422)
KAZAN = place("Казань", "Татарстан", 55.79, 49.12, "Europe/Moscow", 551487)
OMSK = place("Омск", "Омская область", 54.99, 73.37, "Asia/Omsk", 1496153)
VLADIVOSTOK = place("Владивосток", "Приморский край", 43.11, 131.87, "Asia/Vladivostok", 2013348)


async def names(client, auth, user_id: int = 1) -> list[str]:
    listed = await client.get("/api/me/cities", headers=auth(user_id))
    assert listed.status_code == 200
    return [city["name"] for city in listed.json()]


async def test_extra_cities_round_trip(client, auth) -> None:
    assert (await client.get("/api/me/cities", headers=auth())).json() == []
    added = await client.post("/api/me/cities", json=TULA, headers=auth())
    assert added.status_code == 201
    tula = added.json()
    assert tula == {"id": tula["id"], **TULA}
    sochi = (await client.post("/api/me/cities", json=SOCHI, headers=auth())).json()
    # Without a GeoNames id, a region or a country, as a search may give a place.
    bare = {"name": "Казань", "lat": 55.79, "lon": 49.12, "timezone": "Europe/Moscow"}
    kazan = (await client.post("/api/me/cities", json=bare, headers=auth())).json()
    assert kazan == {"id": kazan["id"], "admin": None, "country": None, "geo_id": None, **bare}
    listed = (await client.get("/api/me/cities", headers=auth())).json()
    assert listed == [tula, sochi, kazan]  # in the order they came
    deleted = await client.delete(f"/api/me/cities/{tula['id']}", headers=auth())
    assert deleted.status_code == 204
    assert await names(client, auth) == ["Сочи", "Казань"]
    again = await client.delete(f"/api/me/cities/{tula['id']}", headers=auth())
    assert again.status_code == 404
    assert (again.json()["code"], again.json()["entity"]) == ("not_found", "city")


async def test_a_found_place_is_added_as_it_came(client, auth, meteo) -> None:
    meteo.cities = [City(**TULA)]
    found = (await client.get("/api/cities", params={"q": "Тула"}, headers=auth())).json()
    assert found == [TULA]
    added = await client.post("/api/me/cities", json=found[0], headers=auth())
    assert added.status_code == 201 and added.json() == {"id": added.json()["id"], **TULA}


async def test_a_fifth_city_is_409(client, auth) -> None:
    for city in (TULA, SOCHI, KAZAN, OMSK):
        assert (await client.post("/api/me/cities", json=city, headers=auth())).status_code == 201
    over = await client.post("/api/me/cities", json=VLADIVOSTOK, headers=auth())
    assert over.status_code == 409
    assert over.json() == {
        "type": "about:blank",
        "title": "Limit reached",
        "status": 409,
        "code": "limit_reached",
        "entity": "city",
        "limit": 4,
    }
    assert await names(client, auth) == ["Тула", "Сочи", "Казань", "Омск"]


@pytest.mark.parametrize(
    "city",
    [
        {**TULA, "lat": 54.3},  # the same GeoNames place, found a little elsewhere
        {**TULA, "name": "Тула-2", "lat": 54.195, "geo_id": None},  # no id: the same place
        {**TULA, "name": "Москва", "lat": 55.75, "lon": 37.62, "geo_id": 524901},  # the home city
    ],
)
async def test_a_city_already_there_is_a_422_duplicate(client, auth, city) -> None:
    await client.post("/api/me/cities", json=TULA, headers=auth())
    response = await client.post("/api/me/cities", json=city, headers=auth())
    assert response.status_code == 422
    assert response.json() == {
        "type": "about:blank",
        "title": "Invalid input",
        "status": 422,
        "code": "validation_error",
        "field": "city",
        "reason": "duplicate",
    }
    assert await names(client, auth) == ["Тула"]


@pytest.mark.parametrize(
    ("change", "field", "reason", "limit"),
    [
        ({"timezone": "Mars/Olympus"}, "city", "invalid", None),  # the server's tzdb decides
        ({"name": " \t "}, "city", "invalid", None),  # nothing left of the name
        ({"name": ""}, "name", None, 1),
        ({"name": "Т" * 101}, "name", None, 100),
        ({"admin": "Т" * 101}, "admin", None, 100),
        ({"lat": 91}, "lat", None, 90),
        ({"lon": -180.5}, "lon", None, -180),
        ({"timezone": ""}, "timezone", None, 1),
        ({"geo_id": 0}, "geo_id", None, 1),
        ({"geo_id": 2**63}, "geo_id", None, 2**63 - 1),
        ({"id": 7}, "id", None, None),  # the server gives the id
    ],
)
async def test_an_invalid_city_is_422(client, auth, change, field, reason, limit) -> None:
    response = await client.post("/api/me/cities", json={**TULA, **change}, headers=auth())
    assert response.status_code == 422
    body = response.json()
    assert (body["code"], body["field"]) == ("validation_error", field)
    assert (body.get("reason"), body.get("limit")) == (reason, limit)
    assert await names(client, auth) == []


async def test_another_users_city_stays_out_of_reach(client, auth) -> None:
    mine = (await client.post("/api/me/cities", json=TULA, headers=auth(1))).json()
    assert await names(client, auth, 2) == []
    response = await client.delete(f"/api/me/cities/{mine['id']}", headers=auth(2))
    assert response.status_code == 404 and response.json()["entity"] == "city"
    # The other user may keep the same place: lists are per user.
    assert (await client.post("/api/me/cities", json=TULA, headers=auth(2))).status_code == 201
    assert await names(client, auth, 1) == ["Тула"]


async def test_extra_cities_leave_the_home_city_and_the_reminders_alone(client, auth) -> None:
    rule = {"repeat": "daily", "time_local": "21:00"}
    created = await client.post(
        "/api/reminders", json={"text": "таблетки", "rule": rule}, headers=auth()
    )
    me = (await client.get("/api/me", headers=auth())).json()
    omsk = (await client.post("/api/me/cities", json=OMSK, headers=auth())).json()
    assert (await client.get("/api/me", headers=auth())).json() == me
    await client.delete(f"/api/me/cities/{omsk['id']}", headers=auth())
    assert (await client.get("/api/me", headers=auth())).json() == me
    reminders = (await client.get("/api/reminders", headers=auth())).json()
    assert [(item["id"], item["due_at"]) for item in reminders] == [
        (created.json()["id"], created.json()["due_at"])
    ]


async def test_the_new_home_leaves_the_extra_cities(client, auth) -> None:
    for city in (TULA, SOCHI, KAZAN):
        await client.post("/api/me/cities", json=city, headers=auth())
    # By its GeoNames id, though this search found it farther than 0.01° from the list's.
    home = {"name": "Тула", "lat": 54.25, "lon": 37.6, "timezone": "Europe/Moscow"}
    moved = await client.put("/api/me/city", json={**home, "geo_id": 480562}, headers=auth())
    assert moved.status_code == 200 and moved.json()["city"]["name"] == "Тула"
    assert await names(client, auth) == ["Сочи", "Казань"]
    # Without an id, by its place.
    home = {"name": "Казань", "lat": 55.795, "lon": 49.115, "timezone": "Europe/Moscow"}
    assert (await client.put("/api/me/city", json=home, headers=auth())).status_code == 200
    assert await names(client, auth) == ["Сочи"]
    # Another city stays.
    home = {"name": "Омск", "lat": 54.99, "lon": 73.37, "timezone": "Asia/Omsk", "geo_id": 1}
    assert (await client.put("/api/me/city", json=home, headers=auth())).status_code == 200
    assert await names(client, auth) == ["Сочи"]
    # The home city is never on the list, so it cannot be added back.
    again = await client.post("/api/me/cities", json=OMSK, headers=auth())
    assert again.status_code == 422 and again.json()["reason"] == "duplicate"


@pytest.mark.parametrize(("geo_id", "limit"), [(0, 1), (2**63, 2**63 - 1)])
async def test_the_home_city_geo_id_is_checked(client, auth, geo_id, limit) -> None:
    home = {"name": "Тула", "lat": 54.19, "lon": 37.62, "timezone": "Europe/Moscow"}
    response = await client.put("/api/me/city", json={**home, "geo_id": geo_id}, headers=auth())
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["limit"]) == ("geo_id", limit)
    assert (await client.get("/api/me", headers=auth())).json()["city"]["name"] == "Москва"


async def test_a_move_reschedules_the_repeats_by_the_app_clock(client, auth) -> None:
    rule = {"repeat": "daily", "time_local": "21:00"}
    await client.post("/api/reminders", json={"text": "таблетки", "rule": rule}, headers=auth())
    home = {"name": "Новосибирск", "lat": 55.03, "lon": 82.92, "timezone": "Asia/Novosibirsk"}
    await client.put("/api/me/city", json=home, headers=auth())
    reminders = (await client.get("/api/reminders", headers=auth())).json()
    # 21:00 of the same day in Novosibirsk is 14:00 UTC, still after the app's 12:00.
    assert reminders[0]["due_at"] == "2026-09-28T14:00:00Z"
