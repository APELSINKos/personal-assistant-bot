from __future__ import annotations


async def test_habit_lifecycle_and_marks(client, auth) -> None:
    created = await client.post("/api/habits", json={"name": "Спорт"}, headers=auth())
    assert created.status_code == 201
    habit = created.json()
    assert habit["created_on"] == "2026-09-28" and habit["done_today"] is None
    assert habit["last_days"] == [None] * 9
    marked = await client.put(
        f"/api/habits/{habit['id']}/marks/2026-09-28", json={"done": True}, headers=auth()
    )
    assert marked.status_code == 200
    assert marked.json()["done_today"] is True and marked.json()["streak"] == 1
    cleared = await client.put(
        f"/api/habits/{habit['id']}/marks/2026-09-28", json={"done": None}, headers=auth()
    )
    assert cleared.json()["done_today"] is None
    listed = await client.get("/api/habits", headers=auth())
    assert [h["name"] for h in listed.json()] == ["Спорт"]
    assert (await client.delete(f"/api/habits/{habit['id']}", headers=auth())).status_code == 204


async def test_habit_rules(client, auth) -> None:
    await client.post("/api/habits", json={"name": "Спорт"}, headers=auth())
    duplicate = await client.post("/api/habits", json={"name": "СПОРТ"}, headers=auth())
    assert duplicate.status_code == 422 and duplicate.json()["reason"] == "duplicate"
    habit_id = (await client.get("/api/habits", headers=auth())).json()[0]["id"]
    for day in ("2026-09-27", "2026-09-29"):  # before creation, in the future
        response = await client.put(
            f"/api/habits/{habit_id}/marks/{day}", json={"done": True}, headers=auth()
        )
        assert response.status_code == 422 and response.json()["reason"] == "out_of_range"
