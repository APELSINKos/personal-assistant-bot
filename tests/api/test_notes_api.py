from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from tests.api.conftest import NOW

ITEM_LENGTH = {
    "type": "about:blank",
    "title": "Invalid input",
    "status": 422,
    "code": "validation_error",
    "field": "items",
    "reason": "length",
    "limit": 100,
}


def limit_reached(entity: str, limit: int) -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "Limit reached",
        "status": 409,
        "code": "limit_reached",
        "entity": entity,
        "limit": limit,
    }


async def new_note(client, auth, text: str, **fields: Any) -> dict[str, Any]:
    created = await client.post("/api/notes", json={"text": text, **fields}, headers=auth())
    assert created.status_code == 201, created.json()
    return created.json()


async def listed(client, auth) -> list[dict[str, Any]]:
    response = await client.get("/api/notes", headers=auth())
    assert response.status_code == 200
    return response.json()


async def test_note_lifecycle(client, auth) -> None:
    created = await client.post("/api/notes", json={"text": "  купить хлеб  "}, headers=auth())
    assert created.status_code == 201 and created.json()["text"] == "купить хлеб"
    assert (created.json()["pinned"], created.json()["items"]) == (False, [])
    note_id = created.json()["id"]
    edited = await client.patch(
        f"/api/notes/{note_id}", json={"text": "купить молоко"}, headers=auth()
    )
    assert edited.status_code == 200 and edited.json()["text"] == "купить молоко"
    assert [n["text"] for n in await listed(client, auth)] == ["купить молоко"]
    assert (await client.delete(f"/api/notes/{note_id}", headers=auth())).status_code == 204
    assert await listed(client, auth) == []


async def test_the_newest_note_comes_first_stamped_by_the_app_clock(client, auth) -> None:
    for text in ("первая", "вторая"):
        created = await client.post("/api/notes", json={"text": text}, headers=auth())
        assert created.json()["created_at"] == "2026-09-28T12:00:00Z"  # tests/api/conftest NOW
    assert [note["text"] for note in await listed(client, auth)] == ["вторая", "первая"]


async def test_a_checklist_is_created_with_its_items_and_pin(client, auth) -> None:
    items = [" молоко ", "хлеб\tбородинский", "  " + "я" * 100 + "  "]  # 100 after trimming
    note = await new_note(client, auth, "Покупки", items=items, pinned=True)
    milk, bread, long = note["items"]
    assert note == {
        "id": note["id"],
        "text": "Покупки",
        "pinned": True,
        "items": [
            {"id": milk["id"], "text": "молоко", "done": False},
            {"id": bread["id"], "text": "хлеб бородинский", "done": False},
            {"id": long["id"], "text": "я" * 100, "done": False},
        ],
        "created_at": "2026-09-28T12:00:00Z",
        "updated_at": "2026-09-28T12:00:00Z",
    }
    assert milk["id"] < bread["id"] < long["id"]
    assert await listed(client, auth) == [note]


async def test_pinned_notes_come_first_the_last_pinned_on_top(client, auth, clock) -> None:
    ids = [(await new_note(client, auth, text))["id"] for text in ("первая", "вторая", "третья")]
    for minutes, note_id in ((1, ids[0]), (2, ids[2]), (3, ids[0])):  # the third one is a repeat
        clock[0] = NOW + timedelta(minutes=minutes)
        pinned = await client.patch(f"/api/notes/{note_id}", json={"pinned": True}, headers=auth())
        assert pinned.status_code == 200
    await new_note(client, auth, "четвёртая")
    assert [(note["text"], note["pinned"]) for note in await listed(client, auth)] == [
        ("третья", True),
        ("первая", True),  # pinned again: it keeps its first pin and its place
        ("четвёртая", False),
        ("вторая", False),
    ]


async def test_a_pin_leaves_the_note_as_it_was(client, auth, clock) -> None:
    note = await new_note(client, auth, "Пароль от wifi: hunter2")
    clock[0] = NOW + timedelta(hours=1)
    path = f"/api/notes/{note['id']}"
    pinned = await client.patch(path, json={"pinned": True}, headers=auth())
    assert pinned.status_code == 200 and pinned.json() == {**note, "pinned": True}
    for _ in range(2):  # unpinning a note that is not pinned changes nothing either
        unpinned = await client.patch(path, json={"pinned": False}, headers=auth())
        assert unpinned.status_code == 200 and unpinned.json() == note


async def test_text_and_pin_change_in_one_request(client, auth) -> None:
    note = await new_note(client, auth, "черновик")
    changed = await client.patch(
        f"/api/notes/{note['id']}", json={"text": "Пароль", "pinned": True}, headers=auth()
    )
    assert changed.status_code == 200
    assert (changed.json()["text"], changed.json()["pinned"]) == ("Пароль", True)
    assert [(n["text"], n["pinned"]) for n in await listed(client, auth)] == [("Пароль", True)]


async def test_five_notes_can_be_pinned(client, auth) -> None:
    pinned = [await new_note(client, auth, f"важное {n}", pinned=True) for n in range(5)]
    refused = await client.post(
        "/api/notes", json={"text": "шестая", "pinned": True}, headers=auth()
    )
    assert refused.status_code == 409 and refused.json() == limit_reached("pinned_note", 5)
    assert len(await listed(client, auth)) == 5  # the note is not created either
    plain = await new_note(client, auth, "шестая")
    pin = await client.patch(f"/api/notes/{plain['id']}", json={"pinned": True}, headers=auth())
    assert pin.status_code == 409 and pin.json() == limit_reached("pinned_note", 5)
    # A pinned note pinned again is not a sixth one.
    first = f"/api/notes/{pinned[0]['id']}"
    assert (await client.patch(first, json={"pinned": True}, headers=auth())).status_code == 200
    await client.patch(first, json={"pinned": False}, headers=auth())
    pin = await client.patch(f"/api/notes/{plain['id']}", json={"pinned": True}, headers=auth())
    assert pin.status_code == 200 and pin.json()["pinned"] is True


async def test_a_refused_half_of_a_change_keeps_the_whole_note(client, auth) -> None:
    for number in range(5):
        await new_note(client, auth, f"важное {number}", pinned=True)
    note = await new_note(client, auth, "черновик")
    path = f"/api/notes/{note['id']}"
    refused = await client.patch(path, json={"text": "чистовик", "pinned": True}, headers=auth())
    assert refused.status_code == 409 and refused.json() == limit_reached("pinned_note", 5)
    assert [item for item in await listed(client, auth) if item["id"] == note["id"]] == [note]
    unpin = (await listed(client, auth))[0]["id"]  # room for one more pin
    await client.patch(f"/api/notes/{unpin}", json={"pinned": False}, headers=auth())
    bad = await client.patch(path, json={"text": "  ", "pinned": True}, headers=auth())
    assert bad.status_code == 422
    assert (bad.json()["field"], bad.json()["reason"], bad.json()["limit"]) == (
        "text",
        "length",
        500,
    )
    assert [item for item in await listed(client, auth) if item["id"] == note["id"]] == [note]


@pytest.mark.parametrize(
    ("body", "field", "reason"),
    [
        ({}, "note", "empty"),
        ({"text": None, "pinned": None}, "note", "empty"),
        ({"items": ["хлеб"]}, "items", None),  # items have routes of their own
        ({"pinned": "maybe"}, "pinned", None),
    ],
)
async def test_an_empty_or_unknown_patch_is_422(client, auth, body, field, reason) -> None:
    note = await new_note(client, auth, "заметка")
    response = await client.patch(f"/api/notes/{note['id']}", json=body, headers=auth())
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert (response.json()["field"], response.json().get("reason")) == (field, reason)
    assert await listed(client, auth) == [note]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "text"),
        ({"text": "Покупки", "items": "молоко"}, "items"),
        ({"text": "Покупки", "items": ["молоко", 5]}, "items.1"),
        ({"text": "Покупки", "pinned": "maybe"}, "pinned"),
        ({"text": "Покупки", "done": True}, "done"),
    ],
)
async def test_a_malformed_new_note_is_422(client, auth, body, field) -> None:
    response = await client.post("/api/notes", json=body, headers=auth())
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == ("validation_error", field)
    assert await listed(client, auth) == []


@pytest.mark.parametrize("items", [[""], ["   "], ["молоко", "я" * 101], ["\n"]])
async def test_an_empty_or_long_item_is_422(client, auth, items) -> None:
    response = await client.post(
        "/api/notes", json={"text": "Покупки", "items": items}, headers=auth()
    )
    assert response.status_code == 422 and response.json() == ITEM_LENGTH
    assert await listed(client, auth) == []


async def test_a_note_holds_up_to_twenty_items(client, auth) -> None:
    many = [f"пункт {number}" for number in range(21)]
    over = await client.post("/api/notes", json={"text": "Много", "items": many}, headers=auth())
    assert over.status_code == 409 and over.json() == limit_reached("note_item", 20)
    assert await listed(client, auth) == []
    full = await new_note(client, auth, "Много", items=many[:20])
    assert len(full["items"]) == 20
    extra = await client.post(
        f"/api/notes/{full['id']}/items", json={"text": "ещё"}, headers=auth()
    )
    assert extra.status_code == 409 and extra.json() == limit_reached("note_item", 20)
    assert len((await listed(client, auth))[0]["items"]) == 20


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
    # A checklist's title is required too.
    untitled = await client.post(
        "/api/notes", json={"text": " ", "items": ["молоко"]}, headers=auth()
    )
    assert untitled.status_code == 422 and untitled.json()["field"] == "text"
    for number in range(50):
        await client.post("/api/notes", json={"text": f"n{number}"}, headers=auth())
    over = await client.post("/api/notes", json={"text": "51"}, headers=auth())
    assert over.status_code == 409 and over.json() == limit_reached("note", 50)


async def test_items_are_added_checked_and_deleted(client, auth, clock) -> None:
    note = await new_note(client, auth, "Покупки", items=["молоко"])
    milk = note["items"][0]
    clock[0] = NOW + timedelta(hours=1)
    path = f"/api/notes/{note['id']}/items"
    added = await client.post(path, json={"text": " хлеб "}, headers=auth())
    assert added.status_code == 201
    bread = added.json()
    assert bread == {"id": bread["id"], "text": "хлеб", "done": False} and bread["id"] > milk["id"]
    checked = await client.patch(f"{path}/{bread['id']}", json={"done": True}, headers=auth())
    assert checked.status_code == 200 and checked.json() == {**bread, "done": True}
    # The state is set, not switched: the same request again changes nothing.
    again = await client.patch(f"{path}/{bread['id']}", json={"done": True}, headers=auth())
    assert again.status_code == 200 and again.json() == {**bread, "done": True}
    # Items are not edits of the note: its moments stay.
    assert await listed(client, auth) == [{**note, "items": [milk, {**bread, "done": True}]}]
    deleted = await client.delete(f"{path}/{milk['id']}", headers=auth())
    assert deleted.status_code == 204
    unchecked = await client.patch(f"{path}/{bread['id']}", json={"done": False}, headers=auth())
    assert unchecked.json() == bread
    assert await listed(client, auth) == [{**note, "items": [bread]}]
    gone = await client.delete(f"{path}/{milk['id']}", headers=auth())
    assert gone.status_code == 404
    assert (gone.json()["code"], gone.json()["entity"]) == ("not_found", "note_item")


async def test_clearing_removes_the_checked_items(client, auth) -> None:
    note = await new_note(client, auth, "Покупки", items=["молоко", "хлеб", "сыр"])
    milk, bread, cheese = note["items"]
    path = f"/api/notes/{note['id']}/items"
    for item in (milk, cheese):
        await client.patch(f"{path}/{item['id']}", json={"done": True}, headers=auth())
    cleared = await client.delete(f"{path}?done=true", headers=auth())
    assert cleared.status_code == 204
    assert (await listed(client, auth))[0]["items"] == [bread]
    # Nothing checked is nothing to remove, and fine too.
    assert (await client.delete(f"{path}?done=true", headers=auth())).status_code == 204
    assert (await listed(client, auth))[0]["items"] == [bread]


@pytest.mark.parametrize("query", ["", "?done=false", "?done=1", "?done=True", "?checked=true"])
async def test_clearing_needs_done_true(client, auth, query) -> None:
    note = await new_note(client, auth, "Покупки", items=["молоко"])
    path = f"/api/notes/{note['id']}/items"
    await client.patch(f"{path}/{note['items'][0]['id']}", json={"done": True}, headers=auth())
    response = await client.delete(f"{path}{query}", headers=auth())
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == ("validation_error", "done")
    assert len((await listed(client, auth))[0]["items"]) == 1


async def test_item_requests_are_validated_and_stay_within_their_note(client, auth) -> None:
    note = await new_note(client, auth, "Покупки", items=["молоко"])
    other = await new_note(client, auth, "Дела", items=["позвонить"])
    path = f"/api/notes/{note['id']}/items"
    for text in ("", "   ", "\t", "я" * 101):
        response = await client.post(path, json={"text": text}, headers=auth())
        assert response.status_code == 422 and response.json() == ITEM_LENGTH
    for body, field in (({}, "text"), ({"text": "хлеб", "done": True}, "done")):
        response = await client.post(path, json=body, headers=auth())
        assert response.status_code == 422 and response.json()["field"] == field
    item = f"{path}/{note['items'][0]['id']}"
    for body, field in (
        ({}, "done"),
        ({"done": None}, "done"),
        ({"done": True, "text": "x"}, "text"),
    ):
        response = await client.patch(item, json=body, headers=auth())
        assert response.status_code == 422 and response.json()["field"] == field
    # Another note's item is not found through this one.
    foreign = f"{path}/{other['items'][0]['id']}"
    for method, body in (("PATCH", {"done": True}), ("DELETE", None)):
        response = await client.request(method, foreign, json=body, headers=auth())
        assert response.status_code == 404 and response.json()["entity"] == "note_item"
    assert await listed(client, auth) == [other, note]


async def test_the_items_of_a_gone_note_are_404(client, auth) -> None:
    note = await new_note(client, auth, "Покупки", items=["молоко"])
    item = note["items"][0]["id"]
    await client.delete(f"/api/notes/{note['id']}", headers=auth())
    path = f"/api/notes/{note['id']}/items"
    for method, url, body in [
        ("PATCH", f"/api/notes/{note['id']}", {"pinned": True}),
        ("POST", path, {"text": "хлеб"}),
        ("PATCH", f"{path}/{item}", {"done": True}),
        ("DELETE", f"{path}/{item}", None),
        ("DELETE", f"{path}?done=true", None),
    ]:
        response = await client.request(method, url, json=body, headers=auth())
        assert response.status_code == 404, (method, url)
        assert (response.json()["code"], response.json()["entity"]) == ("not_found", "note")


async def test_foreign_or_missing_ids_are_404(client, auth) -> None:
    mine = await new_note(client, auth, "моё", items=["молоко"], pinned=True)
    item = mine["items"][0]["id"]
    for method, path, body in [
        ("PATCH", f"/api/notes/{mine['id']}", {"text": "чужое"}),
        ("PATCH", f"/api/notes/{mine['id']}", {"pinned": False}),
        ("DELETE", f"/api/notes/{mine['id']}", None),
        ("POST", f"/api/notes/{mine['id']}/items", {"text": "чужое"}),
        ("PATCH", f"/api/notes/{mine['id']}/items/{item}", {"done": True}),
        ("DELETE", f"/api/notes/{mine['id']}/items/{item}", None),
        ("DELETE", f"/api/notes/{mine['id']}/items?done=true", None),
        ("DELETE", "/api/notes/999999", None),
        ("DELETE", "/api/reminders/999999", None),
        ("DELETE", "/api/habits/999999", None),
        ("PUT", "/api/habits/999999/marks/2026-09-28", {"done": True}),
    ]:
        response = await client.request(method, path, json=body, headers=auth(2))
        assert response.status_code == 404, (method, path)
        assert response.json()["code"] == "not_found"
    assert await listed(client, auth) == [mine]
