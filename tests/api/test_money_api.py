from __future__ import annotations


async def categories(client, auth, user_id: int = 1) -> dict[str, int]:
    """The ids of the categories by name (the presets in Russian)."""
    found = await client.get("/api/money/categories", headers=auth(user_id))
    return {
        item["name"] + ("+" if item["kind"] == "income" else ""): item["id"]
        for item in found.json()
    }


async def add(client, auth, **body: object) -> dict:
    created = await client.post("/api/money/entries", json=body, headers=auth())
    assert created.status_code == 201, created.json()
    return created.json()


async def test_a_first_visit_has_the_presets_and_an_empty_month(client, auth) -> None:
    month = (await client.get("/api/money", headers=auth())).json()
    assert (month["month"], month["first_month"], month["currency"]) == ("2026-09", None, "RUB")
    assert (month["spent"], month["income"], month["balance"], month["budget"]) == (0, 0, 0, None)
    assert len(month["days"]) == 30 and month["days"][27] == 0 and month["days"][28] is None
    names = [(item["name"], item["kind"], item["can_hide"]) for item in month["categories"]]
    assert names[0] == ("Продукты", "expense", True)
    assert ("Другое", "expense", False) in names and ("Другое", "income", False) in names
    assert len(names) == 16 and month["entries"] == []


async def test_an_entry_goes_in_and_shows_in_the_month(client, auth) -> None:
    ids = await categories(client, auth)
    saved = await add(client, auth, amount="430.50", category_id=ids["Кафе"], note="кофе")
    entry = saved["entry"]
    assert (entry["amount"], entry["note"], entry["day"], saved["alerts"]) == (
        43050, "кофе", "2026-09-28", [],
    )  # fmt: skip
    month = (await client.get("/api/money", headers=auth())).json()
    assert (month["spent"], month["first_month"], month["days"][27]) == (43050, "2026-09", 43050)
    assert month["expenses"] == [
        {"category_id": ids["Кафе"], "amount": 43050, "share": 100, "left": None}
    ]
    assert month["entries"] == [entry]


async def test_a_bad_entry_is_refused_by_field(client, auth) -> None:
    ids = await categories(client, auth)
    stranger = await categories(client, auth, 2)
    for body, field in (
        ({"amount": "0", "category_id": ids["Кафе"]}, "amount"),
        ({"amount": "1.234", "category_id": ids["Кафе"]}, "amount"),
        ({"amount": "-5", "category_id": ids["Кафе"]}, "amount"),
        ({"amount": "1000000000.01", "category_id": ids["Кафе"]}, "amount"),
        ({"amount": "1", "category_id": ids["Кафе"], "note": "ж" * 101}, "note"),
        ({"amount": "1", "category_id": ids["Кафе"], "day": "2026-09-29"}, "day"),
    ):
        refused = await client.post("/api/money/entries", json=body, headers=auth())
        assert refused.status_code == 422 and refused.json()["field"] == field, body
    theirs = {"amount": "1", "category_id": stranger["Кафе"]}
    assert (await client.post("/api/money/entries", json=theirs, headers=auth())).status_code == 404
    extra = {"amount": "1", "category_id": ids["Кафе"], "user_id": 2}
    assert (await client.post("/api/money/entries", json=extra, headers=auth())).status_code == 422


async def test_an_entry_changes_and_goes(client, auth) -> None:
    ids = await categories(client, auth)
    entry = (await add(client, auth, amount="250", category_id=ids["Кафе"]))["entry"]
    changed = await client.patch(
        f"/api/money/entries/{entry['id']}",
        json={
            "amount": "5000",
            "category_id": ids["Зарплата+"],
            "note": "аванс",
            "day": "2026-09-01",
        },
        headers=auth(),
    )
    assert changed.status_code == 200
    body = changed.json()["entry"]
    assert (body["amount"], body["category_id"], body["note"], body["day"]) == (
        500000, ids["Зарплата+"], "аванс", "2026-09-01",
    )  # fmt: skip
    one = await client.get(f"/api/money/entries/{entry['id']}", headers=auth())
    assert one.json() == body
    theirs = await client.get(f"/api/money/entries/{entry['id']}", headers=auth(2))
    assert theirs.status_code == 404
    month = (await client.get("/api/money", headers=auth())).json()
    assert (month["spent"], month["income"]) == (0, 500000)
    assert (
        await client.delete(f"/api/money/entries/{entry['id']}", headers=auth())
    ).status_code == 204
    assert (
        await client.delete(f"/api/money/entries/{entry['id']}", headers=auth())
    ).status_code == 404
    gone = await client.patch(
        f"/api/money/entries/{entry['id']}", json={"note": "x"}, headers=auth()
    )
    assert gone.status_code == 404
    assert (
        await client.get(f"/api/money/entries/{entry['id']}", headers=auth())
    ).status_code == 404


async def test_a_budget_warning_comes_once(client, auth) -> None:
    ids = await categories(client, auth)
    budget = await client.put("/api/money/budget", json={"amount": "1000"}, headers=auth())
    assert budget.json()["money_budget"] == 100000
    assert (await add(client, auth, amount="790", category_id=ids["Кафе"]))["alerts"] == []
    warned = await add(client, auth, amount="20", category_id=ids["Кафе"])
    assert warned["alerts"] == [
        {
            "category_id": None, "emoji": None, "name": None, "threshold": 80, "spent": 81000,
            "budget": 100000,
        }
    ]  # fmt: skip
    assert (await add(client, auth, amount="1", category_id=ids["Кафе"]))["alerts"] == []
    url = f"/api/money/categories/{ids['Транспорт']}"
    await client.patch(url, json={"budget": "100"}, headers=auth())
    over = await add(client, auth, amount="150", category_id=ids["Транспорт"])
    assert over["alerts"] == [
        {
            "category_id": ids["Транспорт"], "emoji": "🚌", "name": "Транспорт", "threshold": 100,
            "spent": 15000, "budget": 10000,
        }
    ]  # fmt: skip
    removed = await client.put("/api/money/budget", json={"amount": None}, headers=auth())
    assert removed.json()["money_budget"] is None


async def test_categories_are_made_renamed_hidden_and_budgeted(client, auth) -> None:
    ids = await categories(client, auth)
    made = await client.post(
        "/api/money/categories",
        json={"kind": "expense", "name": "Фастфуд", "emoji": "🍔"},
        headers=auth(),
    )
    assert made.status_code == 201
    own = made.json()
    assert (own["name"], own["emoji"], own["hidden"], own["can_hide"]) == (
        "Фастфуд",
        "🍔",
        False,
        True,
    )
    for body, field in (
        ({"kind": "expense", "name": "фастфуд", "emoji": "🍕"}, "name"),
        ({"kind": "expense", "name": "Цели", "emoji": "🎯"}, "emoji"),
    ):
        refused = await client.post("/api/money/categories", json=body, headers=auth())
        assert refused.status_code == 422 and refused.json()["field"] == field
    url = f"/api/money/categories/{own['id']}"
    for change, key, value in (
        ({"name": "Еда навынос"}, "name", "Еда навынос"),
        ({"hidden": True}, "hidden", True),
        ({"budget": "5000"}, "budget", 500000),
        ({"budget": None}, "budget", None),
        ({}, "name", "Еда навынос"),
    ):
        changed = await client.patch(url, json=change, headers=auth())
        assert changed.status_code == 200 and changed.json()[key] == value, change
    for category, change, field in (
        (ids["Другое"], {"hidden": True}, "hidden"),
        (ids["Зарплата+"], {"budget": "100"}, "budget"),
    ):
        refused = await client.patch(
            f"/api/money/categories/{category}", json=change, headers=auth()
        )
        assert refused.status_code == 422 and refused.json()["field"] == field
    stranger = await categories(client, auth, 2)
    theirs = await client.patch(
        f"/api/money/categories/{stranger['Кафе']}", json={}, headers=auth()
    )
    assert theirs.status_code == 404


async def test_other_months(client, auth) -> None:
    august = (await client.get("/api/money?month=2026-08", headers=auth())).json()
    assert august["month"] == "2026-08" and len(august["days"]) == 31 and None not in august["days"]
    for value in ("2026-13", "26-09", "2026-9"):
        refused = await client.get(f"/api/money?month={value}", headers=auth())
        assert refused.status_code == 422, value


async def test_the_currency_is_set_in_me(client, auth) -> None:
    me = await client.patch("/api/me", json={"currency": "USD"}, headers=auth())
    assert (me.json()["currency"], me.json()["money_budget"]) == ("USD", None)
    assert (await client.get("/api/money", headers=auth())).json()["currency"] == "USD"
    refused = await client.patch("/api/me", json={"currency": "XXX"}, headers=auth())
    assert refused.status_code == 422 and refused.json()["field"] == "currency"


async def test_rates_of_the_day_and_over_30_days(client, auth, cbr) -> None:
    rates = (await client.get("/api/rates/all", headers=auth())).json()
    assert rates["date"] == "2026-09-28"
    assert [(item["code"], item["name"]) for item in rates["currencies"]] == [
        ("USD", "Доллар США"), ("EUR", "Евро"),
    ]  # fmt: skip
    history = (await client.get("/api/rates/history?code=USD", headers=auth())).json()
    assert history["code"] == "USD" and len(history["points"]) == 20
    assert history["points"][0] == {"day": "2026-09-01", "value": 84.0}
    assert (await client.get("/api/rates/history?code=GBP", headers=auth())).status_code == 404
    assert (await client.get("/api/rates/history?code=usd", headers=auth())).status_code == 422
    cbr.fail = True
    assert (await client.get("/api/rates/all", headers=auth())).status_code == 503


async def test_today_has_the_money_of_the_day(client, auth) -> None:
    ids = await categories(client, auth)
    await add(client, auth, amount="430.50", category_id=ids["Кафе"])
    today = (await client.get("/api/today", headers=auth())).json()
    assert today["money"] == {
        "currency": "RUB", "today": 43050, "spent": 43050, "budget": None, "left": None,
        "per_day": None, "count": 1,
    }  # fmt: skip
