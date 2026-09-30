from __future__ import annotations

import pytest

WEEKDAYS_0730 = {"repeat": "weekly", "time_local": "07:30", "weekdays": 31}


async def create(client, auth, **body):
    return await client.post("/api/reminders", json=body, headers=auth())


async def test_create_a_repeat(client, auth) -> None:
    response = await create(client, auth, text="зарядка", rule=WEEKDAYS_0730)
    assert response.status_code == 201
    body = response.json()
    assert (body["repeat"], body["due_local"]) == ("weekly", "2026-09-29T07:30")
    assert body["description"] == "по будням в 07:30"
    # NOTE: the brief's draft expected anchor_date "2026-09-28" (the day the request was made).
    # create_repeating (Task 5 review) stores anchor_date = max(given anchor, local date of the
    # first firing): posted at 15:00 Moscow with a 07:30 rule, the first firing is tomorrow
    # (2026-09-29), so the stored anchor moves to that day. Adapted to the documented behaviour.
    assert body["rule"] == {
        "repeat": "weekly",
        "time_local": "07:30",
        "weekdays": 31,
        "interval_weeks": 1,
        "month_day": None,
        "anchor_date": "2026-09-29",
    }
    listed = (await client.get("/api/reminders", headers=auth())).json()
    assert [r["description"] for r in listed] == ["по будням в 07:30"]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"text": "x"}, "schedule"),
        ({"text": "x", "due_local": "2026-09-29T10:00", "rule": WEEKDAYS_0730}, "schedule"),
        ({"text": "x", "rule": {"repeat": "weekly", "time_local": "07:30"}}, "repeat_invalid"),
        ({"text": "x", "rule": {"repeat": "monthly", "time_local": "07:30"}}, "repeat_invalid"),
    ],
)
async def test_rejected_schedules(client, auth, body, reason) -> None:
    response = await client.post("/api/reminders", json=body, headers=auth())
    assert response.status_code == 422 and response.json()["reason"] == reason


async def test_patch_text_time_and_repeat(client, auth) -> None:
    created = (await create(client, auth, text="a", due_local="2026-09-29T10:00")).json()
    url = f"/api/reminders/{created['id']}"
    patched = await client.patch(url, json={"text": "b", "rule": WEEKDAYS_0730}, headers=auth())
    assert patched.status_code == 200
    assert (patched.json()["text"], patched.json()["repeat"]) == ("b", "weekly")
    back = await client.patch(url, json={"due_local": "2026-10-01T09:00"}, headers=auth())
    assert (back.json()["repeat"], back.json()["due_local"]) == ("none", "2026-10-01T09:00")
    foreign = await client.patch(url, json={"text": "x"}, headers=auth(user_id=2))
    assert foreign.status_code == 404


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "завтра в 9 купить молоко",
            {"text": "купить молоко", "repeat": "none", "date": "2026-09-29", "time": "09:00"},
        ),
        (
            "по будням в 7:30 зарядка",
            {
                "text": "зарядка",
                "repeat": "weekly",
                "time": "07:30",
                "weekdays": 31,
                "description": "по будням в 07:30",
            },
        ),
        (
            "каждый день таблетки",
            {"text": "таблетки", "repeat": "daily", "time": None, "description": None},
        ),
        ("в пятницу купить подарок", {"repeat": "none", "date": "2026-10-02", "time": None}),
    ],
)
async def test_parse(client, auth, text, expected) -> None:
    response = await client.post("/api/reminders/parse", json={"text": text}, headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in expected} == expected


async def test_parse_refuses_plain_text(client, auth) -> None:
    response = await client.post("/api/reminders/parse", json={"text": "привет"}, headers=auth())
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["reason"]) == (
        "text",
        "phrase_not_understood",
    )


async def test_snooze_and_done(client, auth) -> None:
    one_off = (await create(client, auth, text="a", due_local="2026-09-28T16:00")).json()
    moved = await client.post(
        f"/api/reminders/{one_off['id']}/snooze", json={"kind": "10m"}, headers=auth()
    )
    assert moved.status_code == 200 and moved.json()["due_local"] == "2026-09-28T15:10"
    series = (await create(client, auth, text="b", rule=WEEKDAYS_0730)).json()
    copy = await client.post(
        f"/api/reminders/{series['id']}/snooze", json={"kind": "1h"}, headers=auth()
    )
    assert copy.json()["id"] != series["id"] and copy.json()["repeat"] == "none"
    done = await client.post(f"/api/reminders/{one_off['id']}/done", headers=auth())
    assert done.status_code == 204
    foreign = await client.post(f"/api/reminders/{one_off['id']}/done", headers=auth(user_id=2))
    assert foreign.status_code == 404
