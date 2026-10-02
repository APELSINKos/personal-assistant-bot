from __future__ import annotations


async def test_a_habit_has_its_look_goal_and_statistics(client, auth) -> None:
    created = await client.post(
        "/api/habits",
        json={"name": "Бег", "emoji": "🏃", "color": "sky", "weekly_goal": 3},
        headers=auth(),
    )
    assert created.status_code == 201
    habit = created.json()
    assert (habit["emoji"], habit["color"], habit["weekly_goal"]) == ("🏃", "sky", 3)
    assert (habit["streak"], habit["streak_unit"], habit["record"], habit["percent"]) == (
        0,
        "weeks",
        0,
        0,
    )
    # Created on Monday 28 September: this week asks for all 3 days; the rest is ahead.
    assert (habit["week_done"], habit["week_goal"], habit["week"]) == (0, 3, "-......")
    plain = await client.post("/api/habits", json={"name": "Вода"}, headers=auth())
    assert (plain.json()["emoji"], plain.json()["color"], plain.json()["weekly_goal"]) == (
        "🎯",
        "mint",
        7,
    )
    assert plain.json()["streak_unit"] == "days"


async def test_a_habit_cannot_get_a_look_outside_the_set(client, auth) -> None:
    for body, field in (
        ({"name": "Бег", "emoji": "🦄"}, "emoji"),
        ({"name": "Бег", "color": "red"}, "color"),
        ({"name": "Бег", "weekly_goal": 8}, "weekly_goal"),
    ):
        refused = await client.post("/api/habits", json=body, headers=auth())
        assert refused.status_code == 422 and refused.json()["field"] == field


async def test_patch_changes_a_habit(client, auth) -> None:
    habit_id = (await client.post("/api/habits", json={"name": "Бег"}, headers=auth())).json()["id"]
    await client.post("/api/habits", json={"name": "Вода"}, headers=auth())
    changed = await client.patch(
        f"/api/habits/{habit_id}",
        json={"name": "Пробежка", "emoji": "🏃", "color": "coral", "weekly_goal": 4},
        headers=auth(),
    )
    assert changed.status_code == 200
    body = changed.json()
    assert (body["name"], body["emoji"], body["color"], body["weekly_goal"]) == (
        "Пробежка",
        "🏃",
        "coral",
        4,
    )
    assert body["streak_unit"] == "weeks"
    untouched = await client.patch(f"/api/habits/{habit_id}", json={}, headers=auth())
    assert untouched.json()["name"] == "Пробежка"
    for patch, field, reason in (
        ({"name": "ВОДА"}, "name", "duplicate"),
        ({"name": " "}, "name", "length"),
        ({"emoji": "🦄"}, "emoji", "invalid"),
        ({"color": "red"}, "color", "invalid"),
    ):
        refused = await client.patch(f"/api/habits/{habit_id}", json=patch, headers=auth())
        assert refused.status_code == 422
        assert (refused.json()["field"], refused.json()["reason"]) == (field, reason)
    zero = await client.patch(f"/api/habits/{habit_id}", json={"weekly_goal": 0}, headers=auth())
    assert zero.status_code == 422 and zero.json()["field"] == "weekly_goal"
    stranger = await client.patch(f"/api/habits/{habit_id}", json={"name": "x"}, headers=auth(2))
    assert stranger.status_code == 404


async def test_one_habit_comes_with_its_year(client, auth) -> None:
    habit_id = (await client.post("/api/habits", json={"name": "Бег"}, headers=auth())).json()["id"]
    await client.put(
        f"/api/habits/{habit_id}/marks/2026-09-28", json={"done": True}, headers=auth()
    )
    detail = await client.get(f"/api/habits/{habit_id}", headers=auth())
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Бег" and body["streak"] == 1
    assert body["year_from"] == "2025-09-29"  # the Monday 52 weeks before this week's
    assert len(body["year"]) == 371
    assert body["year"].endswith("1" + "." * 6)
    assert (await client.get(f"/api/habits/{habit_id}", headers=auth(2))).status_code == 404
