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
    # A pending one-off due at 16:00, snoozed «+10 мин» at 15:00: never earlier than its own
    # due moment, so this lands at 16:10, not 15:10 (fix round 1, ruling 4).
    assert moved.status_code == 200 and moved.json()["due_local"] == "2026-09-28T16:10"
    foreign_snooze = await client.post(
        f"/api/reminders/{one_off['id']}/snooze", json={"kind": "1h"}, headers=auth(user_id=2)
    )
    assert foreign_snooze.status_code == 404
    listed = {r["id"]: r for r in (await client.get("/api/reminders", headers=auth())).json()}
    assert listed[one_off["id"]]["due_local"] == "2026-09-28T16:10"  # untouched by the stranger
    series = (await create(client, auth, text="b", rule=WEEKDAYS_0730)).json()
    copy = await client.post(
        f"/api/reminders/{series['id']}/snooze", json={"kind": "1h"}, headers=auth()
    )
    assert copy.json()["id"] != series["id"] and copy.json()["repeat"] == "none"
    done = await client.post(f"/api/reminders/{one_off['id']}/done", headers=auth())
    assert done.status_code == 204
    foreign = await client.post(f"/api/reminders/{one_off['id']}/done", headers=auth(user_id=2))
    assert foreign.status_code == 404
    after_done = [r["id"] for r in (await client.get("/api/reminders", headers=auth())).json()]
    assert one_off["id"] not in after_done


async def test_biweekly_rule_starts_at_the_first_matching_day(client, auth) -> None:
    rule = {"repeat": "weekly", "time_local": "10:00", "weekdays": 1, "interval_weeks": 2}
    response = await create(client, auth, text="уборка", rule=rule)
    assert response.status_code == 201
    body = response.json()
    assert body["due_local"] == "2026-10-05T10:00"
    assert body["rule"]["anchor_date"] == "2026-10-05"
    # An explicit anchor of today gives the very same result as leaving it out.
    explicit = await create(
        client, auth, text="уборка2", rule={**rule, "anchor_date": "2026-09-28"}
    )
    assert explicit.json()["due_local"] == "2026-10-05T10:00"
    assert explicit.json()["rule"]["anchor_date"] == "2026-10-05"


async def test_biweekly_phrase_and_the_matching_rule_agree(client, auth) -> None:
    parsed = await client.post(
        "/api/reminders/parse",
        json={"text": "раз в две недели по понедельникам в 10:00 уборка"},
        headers=auth(),
    )
    assert parsed.status_code == 200
    fields = parsed.json()
    rule = {
        "repeat": fields["repeat"],
        "time_local": fields["time"],
        "weekdays": fields["weekdays"],
        "interval_weeks": fields["interval_weeks"],
    }
    created = await create(client, auth, text=fields["text"], rule=rule)
    assert created.json()["due_local"] == "2026-10-05T10:00"


async def test_rule_stores_only_the_fields_its_kind_uses(client, auth) -> None:
    response = await create(
        client,
        auth,
        text="таблетки",
        rule={
            "repeat": "daily",
            "time_local": "09:00",
            "weekdays": 31,
            "month_day": 5,
            "interval_weeks": 2,
        },
    )
    assert response.status_code == 201
    rule = response.json()["rule"]
    assert (rule["weekdays"], rule["month_day"], rule["interval_weeks"]) == (None, None, 1)


async def test_anchor_date_out_of_range_is_rejected(client, auth) -> None:
    response = await create(
        client,
        auth,
        text="x",
        rule={"repeat": "daily", "time_local": "09:00", "anchor_date": "9999-12-31"},
    )
    assert response.status_code == 422
    assert response.json()["reason"] == "repeat_invalid"


async def test_parse_checks_the_text_length(client, auth) -> None:
    response = await client.post(
        "/api/reminders/parse", json={"text": "завтра в 9 " + "x" * 250}, headers=auth()
    )
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["reason"]) == ("text", "length")


async def test_parse_a_phrase_with_no_text_left(client, auth) -> None:
    # The form keeps its own text field: a phrase that is all schedule still fills the rest.
    response = await client.post(
        "/api/reminders/parse", json={"text": "завтра в 9"}, headers=auth()
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["text"], body["date"], body["time"]) == ("", "2026-09-29", "09:00")


async def test_parse_gives_the_first_day_of_a_repeat(client, auth) -> None:
    # Monday 15:00 in Moscow: the first Wednesday of an every-other-week rule is this week's.
    response = await client.post(
        "/api/reminders/parse",
        json={"text": "раз в две недели по средам в 9 практика"},
        headers=auth(),
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["repeat"], body["interval_weeks"], body["date"]) == ("weekly", 2, "2026-09-30")
