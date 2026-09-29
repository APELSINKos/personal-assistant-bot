from __future__ import annotations

import pytest


def _item_paths(item_id: int | str) -> list[tuple[str, str, dict[str, object] | None]]:
    return [
        ("PATCH", f"/api/notes/{item_id}", {"text": "x"}),
        ("DELETE", f"/api/notes/{item_id}", None),
        ("DELETE", f"/api/reminders/{item_id}", None),
        ("DELETE", f"/api/habits/{item_id}", None),
        ("PUT", f"/api/habits/{item_id}/marks/2026-09-28", {"done": True}),
    ]


@pytest.mark.parametrize("item_id", [2**63, 10**30, 0, -1])
async def test_ids_out_of_range_are_422(client, auth, item_id) -> None:
    for method, path, body in _item_paths(item_id):
        response = await client.request(method, path, json=body, headers=auth())
        assert response.status_code == 422, (method, path)
        assert response.json()["code"] == "validation_error"


async def test_largest_id_is_merely_not_found(client, auth) -> None:
    for method, path, body in _item_paths(2**63 - 1):
        response = await client.request(method, path, json=body, headers=auth())
        assert response.status_code == 404, (method, path)


async def test_another_users_items_stay_out_of_reach(client, auth) -> None:
    async def create(user_id: int, name: str) -> dict[str, int]:
        note = await client.post("/api/notes", json={"text": name}, headers=auth(user_id))
        reminder = await client.post(
            "/api/reminders",
            json={"text": name, "due_local": "2026-09-28T19:30"},
            headers=auth(user_id),
        )
        habit = await client.post("/api/habits", json={"name": name}, headers=auth(user_id))
        return {
            "notes": note.json()["id"],
            "reminders": reminder.json()["id"],
            "habits": habit.json()["id"],
        }

    first = await create(1, "первый")
    second = await create(2, "второй")
    for kind in ("notes", "reminders", "habits"):
        listed = (await client.get(f"/api/{kind}", headers=auth(2))).json()
        assert [item["id"] for item in listed] == [second[kind]], kind
    for method, path, body in [
        ("DELETE", f"/api/reminders/{first['reminders']}", None),
        ("DELETE", f"/api/habits/{first['habits']}", None),
        ("PUT", f"/api/habits/{first['habits']}/marks/2026-09-28", {"done": True}),
    ]:
        response = await client.request(method, path, json=body, headers=auth(2))
        assert response.status_code == 404, (method, path)
        assert response.json()["code"] == "not_found"
    reminders = (await client.get("/api/reminders", headers=auth(1))).json()
    assert [reminder["id"] for reminder in reminders] == [first["reminders"]]
    habits = (await client.get("/api/habits", headers=auth(1))).json()
    assert [(habit["id"], habit["done_today"]) for habit in habits] == [(first["habits"], None)]
