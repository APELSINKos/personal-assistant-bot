from __future__ import annotations

from datetime import UTC, datetime

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import GetMe
from sqlalchemy import select

from assistant.core.models import User


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


async def test_a_habit_names_the_day_its_statistics_are_for(client, auth, clock) -> None:
    # The user's day on the server, not the device's: the app marks this day, so a list drawn
    # before midnight marks the day it shows.
    created = await client.post("/api/habits", json={"name": "Спорт"}, headers=auth())
    assert created.json()["day"] == "2026-09-28"
    clock[0] = datetime(2026, 9, 28, 21, 30, tzinfo=UTC)  # 00:30 on the 29th in Moscow
    headers = auth(signed_at=clock[0])
    [listed] = (await client.get("/api/habits", headers=headers)).json()
    assert (listed["day"], listed["done_today"]) == ("2026-09-29", None)
    detail = (await client.get(f"/api/habits/{listed['id']}", headers=headers)).json()
    assert detail["day"] == "2026-09-29"
    today = (await client.get("/api/today", headers=headers)).json()
    assert today["habits"]["items"][0]["day"] == today["date"] == "2026-09-29"


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


async def test_the_card_in_the_chat_says_when_the_bot_may_not_write(
    client, auth, telegram, session
) -> None:
    created = await client.post("/api/habits", json={"name": "Спорт"}, headers=auth())
    path = f"/api/habits/{created.json()['id']}/card"
    assert (await client.post(path, headers=auth())).status_code == 204  # the bot's name is kept
    blocked = "Forbidden: bot was blocked by the user"
    telegram.errors.append(TelegramForbiddenError(method=GetMe(), message=blocked))
    refused = await client.post(path, headers=auth())
    assert (refused.status_code, refused.json()["code"]) == (403, "write_forbidden")
    # The flag is the bot's own: the API never sets it.
    assert await session.scalar(select(User.bot_blocked).where(User.id == 1)) is False
    for error in (
        TelegramBadRequest(method=GetMe(), message="Bad Request: wrong file"),
        TelegramNetworkError(method=GetMe(), message="timeout"),
    ):
        telegram.errors.append(error)
        failed = await client.post(path, headers=auth())
        assert (failed.status_code, failed.json()["code"]) == (503, "upstream_unavailable")
        assert failed.json()["service"] == "telegram"
