from __future__ import annotations

from datetime import UTC, datetime

import pytest

from assistant.core.services import reminders


async def test_create_list_cancel(client, auth) -> None:
    created = await client.post(
        "/api/reminders", json={"text": "созвон", "due_local": "2026-09-28T19:30"}, headers=auth()
    )
    assert created.status_code == 201
    body = created.json()
    assert body["due_at"] == "2026-09-28T16:30:00Z" and body["due_local"] == "2026-09-28T19:30"
    assert body["status"] == "pending"
    listed = await client.get("/api/reminders", headers=auth())
    assert [r["text"] for r in listed.json()] == ["созвон"]
    assert (await client.delete(f"/api/reminders/{body['id']}", headers=auth())).status_code == 204
    assert (await client.get("/api/reminders", headers=auth())).json() == []


@pytest.mark.parametrize(
    ("due_local", "field", "reason"),
    [
        ("2026-09-28T14:00", "when", "past"),
        ("2026-02-30T10:00", "due_local", "format"),
        ("9999-12-31T23:59", "when", "invalid"),
        ("2101-01-01T09:00", "when", "invalid"),
    ],
)
async def test_rejected_moments(client, auth, due_local, field, reason) -> None:
    response = await client.post(
        "/api/reminders", json={"text": "x", "due_local": due_local}, headers=auth()
    )
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["reason"]) == (field, reason)


async def test_an_edit_cannot_move_a_reminder_past_2100(client, auth) -> None:
    created = await client.post(
        "/api/reminders", json={"text": "x", "due_local": "2026-09-29T10:00"}, headers=auth()
    )
    url = f"/api/reminders/{created.json()['id']}"
    response = await client.patch(url, json={"due_local": "9999-12-31T23:59"}, headers=auth())
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["reason"]) == ("when", "invalid")
    listed = await client.get("/api/reminders", headers=auth())
    assert [r["due_local"] for r in listed.json()] == ["2026-09-29T10:00"]


async def test_bad_format_and_status_are_422(client, auth) -> None:
    bad = await client.post(
        "/api/reminders", json={"text": "x", "due_local": "завтра"}, headers=auth()
    )
    assert bad.status_code == 422 and bad.json()["field"] == "due_local"
    other = await client.get("/api/reminders", params={"status": "sent"}, headers=auth())
    assert other.status_code == 422


async def test_due_local_follows_user_zone_and_dst(client, auth, make_user, clock) -> None:
    await make_user(id=5, tz="America/New_York")
    clock[0] = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
    # 02:30 on 8 March 2026 does not exist in New York (clocks jump 02:00 → 03:00).
    created = await client.post(
        "/api/reminders",
        json={"text": "gap", "due_local": "2026-03-08T02:30"},
        headers=auth(5, signed_at=clock[0]),
    )  # initData must be fresh for the API's clock
    assert created.json()["due_local"] == "2026-03-08T03:30"
    assert created.json()["due_at"] == "2026-03-08T07:30:00Z"


async def test_a_text_only_edit_keeps_the_second_pass_of_the_autumn_hour(
    client, auth, make_user, session, clock
) -> None:
    user = await make_user(id=5, tz="Europe/Berlin")
    clock[0] = datetime(2026, 10, 24, 23, 40, tzinfo=UTC)  # 01:40 CEST; at 03:00 it is 02:00 again
    # The bot stores «через …» in the second pass exactly; the list shows only its wall.
    second_pass = datetime(2026, 10, 25, 2, 30, fold=1)  # 02:30 CET
    reminder = await reminders.create(session, user, "чай", second_pass, clock[0])
    await session.commit()
    assert reminder.due_at == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    headers = auth(5, signed_at=clock[0])
    [listed] = (await client.get("/api/reminders", headers=headers)).json()
    assert listed["due_local"] == "2026-10-25T02:30"
    url = f"/api/reminders/{reminder.id}"
    body = {"text": "зелёный чай", "due_local": listed["due_local"]}
    kept = await client.patch(url, json=body, headers=headers)
    assert kept.status_code == 200
    assert (kept.json()["text"], kept.json()["due_at"]) == ("зелёный чай", "2026-10-25T01:30:00Z")
    body["due_local"] = "2026-10-25T03:30"
    moved = await client.patch(url, json=body, headers=headers)
    assert moved.json()["due_at"] == "2026-10-25T02:30:00Z"
