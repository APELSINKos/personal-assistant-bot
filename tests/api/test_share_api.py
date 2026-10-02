from __future__ import annotations

from datetime import timedelta

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe, SavePreparedInlineMessage, SendPhoto
from sqlalchemy import func, select

from assistant.core.models import ShareCard
from tests.api.conftest import NOW


async def _habit(client, auth, name: str = "Спорт", user_id: int = 1) -> int:
    created = await client.post("/api/habits", json={"name": name}, headers=auth(user_id))
    return int(created.json()["id"])


async def _cards(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(ShareCard)))


async def test_sharing_prepares_a_message_with_a_link_to_the_card(
    client, auth, telegram, clock
) -> None:
    habit_id = await _habit(client, auth)
    shared = await client.post(f"/api/habits/{habit_id}/share", headers=auth())
    assert shared.status_code == 200
    assert shared.json() == {"prepared_id": "prepared-1"}
    [prepared] = telegram.of(SavePreparedInlineMessage)
    assert prepared.user_id == 1
    assert prepared.allow_user_chats and prepared.allow_group_chats and prepared.allow_channel_chats
    link = prepared.result.photo_url
    assert link.startswith("https://app.example/api/share/") and link.endswith(".jpg")
    assert prepared.result.thumbnail_url == link
    assert prepared.result.caption == "🎯 Спорт — 0 дней подряд"
    # Telegram downloads the picture without anyone's signature.
    picture = await client.get(link.removeprefix("https://app.example"))
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/jpeg"
    assert picture.content[:2] == b"\xff\xd8"
    # Kept until the prepared message expires (a day) and an hour more, then gone.
    clock[0] = NOW + timedelta(hours=25)
    gone = await client.get(link.removeprefix("https://app.example"))
    assert gone.status_code == 404


async def test_a_wrong_token_finds_no_card(client) -> None:
    for path in ("/api/share/nope.jpg", f"/api/share/{'a' * 43}.jpg", "/api/share/..%2F..%2Fx.jpg"):
        assert (await client.get(path)).status_code == 404


async def test_six_cards_a_minute(client, auth, monotonic) -> None:
    habit_id = await _habit(client, auth)
    for _ in range(3):
        assert (
            await client.post(f"/api/habits/{habit_id}/share", headers=auth())
        ).status_code == 200
        assert (
            await client.post(f"/api/habits/{habit_id}/card", headers=auth())
        ).status_code == 204
    refused = await client.post(f"/api/habits/{habit_id}/share", headers=auth())
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) == 60
    monotonic[0] += 60
    assert (await client.post(f"/api/habits/{habit_id}/card", headers=auth())).status_code == 204


async def test_a_foreign_habit_is_not_found_and_spends_nothing(client, auth) -> None:
    habit_id = await _habit(client, auth, user_id=2)
    for _ in range(7):
        response = await client.post(f"/api/habits/{habit_id}/share", headers=auth())
        assert response.status_code == 404
    own = await _habit(client, auth)
    assert (await client.post(f"/api/habits/{own}/share", headers=auth())).status_code == 200


async def test_when_telegram_refuses_no_card_is_kept(client, auth, telegram, session) -> None:
    habit_id = await _habit(client, auth)
    assert (await client.post(f"/api/habits/{habit_id}/share", headers=auth())).status_code == 200
    assert await _cards(session) == 1
    telegram.errors.append(TelegramNetworkError(method=GetMe(), message="timeout"))
    refused = await client.post(f"/api/habits/{habit_id}/share", headers=auth())
    assert refused.status_code == 503 and refused.json()["code"] == "upstream_unavailable"
    assert await _cards(session) == 1  # the second picture went with the failed message


async def test_an_unreachable_telegram_is_a_503_and_keeps_no_card(
    client, auth, telegram, session
) -> None:
    habit_id = await _habit(client, auth)
    for path in ("share", "card"):  # the bot's name for the card is asked first
        telegram.errors.append(TelegramNetworkError(method=GetMe(), message="timeout"))
        refused = await client.post(f"/api/habits/{habit_id}/{path}", headers=auth())
        assert refused.status_code == 503 and refused.json()["code"] == "upstream_unavailable"
    assert await _cards(session) == 0


async def test_without_the_site_or_the_bot_sharing_is_off(app, client, auth) -> None:
    habit_id = await _habit(client, auth)
    app.state.assistant.site = None
    off = await client.post(f"/api/habits/{habit_id}/share", headers=auth())
    assert off.status_code == 503
    app.state.assistant.bot = None
    for path in ("share", "card"):
        assert (
            await client.post(f"/api/habits/{habit_id}/{path}", headers=auth())
        ).status_code == 503


async def test_the_card_can_be_sent_to_the_bot_chat(client, auth, telegram) -> None:
    habit_id = await _habit(client, auth)
    sent = await client.post(f"/api/habits/{habit_id}/card", headers=auth())
    assert sent.status_code == 204
    [photo] = telegram.of(SendPhoto)
    assert photo.chat_id == 1
    assert photo.caption == "🎯 Спорт — 0 дней подряд"


async def test_the_card_speaks_the_users_language(client, auth, telegram) -> None:
    created = await client.post("/api/habits", json={"name": "Run"}, headers=auth(lang="en"))
    await client.post(f"/api/habits/{created.json()['id']}/card", headers=auth(lang="en"))
    [photo] = telegram.of(SendPhoto)
    assert photo.caption == "🎯 Run — 0 days in a row"
