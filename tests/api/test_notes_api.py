from __future__ import annotations


async def test_note_lifecycle(client, auth) -> None:
    created = await client.post("/api/notes", json={"text": "  купить хлеб  "}, headers=auth())
    assert created.status_code == 201 and created.json()["text"] == "купить хлеб"
    note_id = created.json()["id"]
    edited = await client.patch(
        f"/api/notes/{note_id}", json={"text": "купить молоко"}, headers=auth()
    )
    assert edited.status_code == 200 and edited.json()["text"] == "купить молоко"
    listed = await client.get("/api/notes", headers=auth())
    assert [n["text"] for n in listed.json()] == ["купить молоко"]
    assert (await client.delete(f"/api/notes/{note_id}", headers=auth())).status_code == 204
    assert (await client.get("/api/notes", headers=auth())).json() == []


async def test_the_newest_note_comes_first_stamped_by_the_app_clock(client, auth) -> None:
    for text in ("первая", "вторая"):
        created = await client.post("/api/notes", json={"text": text}, headers=auth())
        assert created.json()["created_at"] == "2026-09-28T12:00:00Z"  # tests/api/conftest NOW
    listed = await client.get("/api/notes", headers=auth())
    assert [note["text"] for note in listed.json()] == ["вторая", "первая"]


async def test_note_validation_and_limit(client, auth) -> None:
    too_long = await client.post("/api/notes", json={"text": "я" * 501}, headers=auth())
    assert too_long.status_code == 422
    assert too_long.json() | {"title": None} == {
        "type": "about:blank",
        "title": None,
        "status": 422,
        "code": "validation_error",
        "field": "text",
        "reason": "length",
        "limit": 500,
    }
    for number in range(50):
        await client.post("/api/notes", json={"text": f"n{number}"}, headers=auth())
    over = await client.post("/api/notes", json={"text": "51"}, headers=auth())
    assert over.status_code == 409 and over.json()["code"] == "limit_reached"
    assert over.json()["limit"] == 50


async def test_foreign_or_missing_ids_are_404(client, auth) -> None:
    mine = (await client.post("/api/notes", json={"text": "моё"}, headers=auth(1))).json()
    for method, path, body in [
        ("PATCH", f"/api/notes/{mine['id']}", {"text": "чужое"}),
        ("DELETE", f"/api/notes/{mine['id']}", None),
        ("DELETE", "/api/notes/999999", None),
        ("DELETE", "/api/reminders/999999", None),
        ("DELETE", "/api/habits/999999", None),
        ("PUT", "/api/habits/999999/marks/2026-09-28", {"done": True}),
    ]:
        response = await client.request(method, path, json=body, headers=auth(2))
        assert response.status_code == 404, (method, path)
        assert response.json()["code"] == "not_found"
    assert (await client.get("/api/notes", headers=auth(1))).json()[0]["text"] == "моё"
