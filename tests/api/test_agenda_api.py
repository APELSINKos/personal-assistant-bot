from __future__ import annotations


async def test_agenda_lists_every_day_with_items(client, auth) -> None:
    rule = {"repeat": "weekly", "time_local": "07:30", "weekdays": 31}
    await client.post("/api/reminders", json={"text": "зарядка", "rule": rule}, headers=auth())
    await client.post(
        "/api/reminders", json={"text": "врач", "due_local": "2026-09-29T10:00"}, headers=auth()
    )
    response = await client.get("/api/agenda?from=2026-09-28&to=2026-10-04", headers=auth())
    assert response.status_code == 200
    days = response.json()["days"]
    assert [day["date"] for day in days] == [
        f"2026-{d}" for d in ("09-28", "09-29", "09-30", "10-01", "10-02", "10-03", "10-04")
    ]
    tuesday = days[1]["items"]
    assert [(i["time"], i["text"], i["repeat"]) for i in tuesday] == [
        ("07:30", "зарядка", "weekly"),
        ("10:00", "врач", "none"),
    ]
    assert tuesday[0]["description"] == "по будням в 07:30"
    assert days[5]["items"] == []  # Saturday


async def test_agenda_follows_the_city_zone(client, auth) -> None:
    await client.put(
        "/api/me/city",
        json={"name": "Нью-Йорк", "lat": 40.71, "lon": -74.0, "timezone": "America/New_York"},
        headers=auth(),
    )
    rule = {"repeat": "daily", "time_local": "20:00"}
    await client.post("/api/reminders", json={"text": "звонок", "rule": rule}, headers=auth())
    days = (await client.get("/api/agenda?from=2026-09-28&to=2026-09-29", headers=auth())).json()
    assert [[i["time"] for i in d["items"]] for d in days["days"]] == [["20:00"], ["20:00"]]


async def test_agenda_range_is_checked(client, auth) -> None:
    backwards = await client.get("/api/agenda?from=2026-10-04&to=2026-09-28", headers=auth())
    too_long = await client.get("/api/agenda?from=2026-01-01&to=2026-12-31", headers=auth())
    far_future = await client.get("/api/agenda?from=9999-12-31&to=9999-12-31", headers=auth())
    far_past = await client.get("/api/agenda?from=0001-01-01&to=0001-01-01", headers=auth())
    for response in (backwards, too_long, far_future, far_past):
        assert response.status_code == 422
        assert (response.json()["field"], response.json()["reason"]) == ("to", "range")


async def test_write_access(client, auth) -> None:
    me = (await client.get("/api/me", headers=auth())).json()
    assert me["can_write"] is False  # opened the app, never wrote to the bot
    allowed = await client.post("/api/me/write-access", headers=auth())
    assert allowed.json()["can_write"] is True
    still = (await client.get("/api/me", headers=auth())).json()
    assert still["can_write"] is True  # the permission persists past the one response


async def test_signed_permission_marks_the_user_writable(client, auth) -> None:
    me = await client.get(
        "/api/me", headers=auth(user_id=5, user_extra={"allows_write_to_pm": True})
    )
    assert me.json()["can_write"] is True
