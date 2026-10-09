"""«Поделиться прогнозом»: the week's forecast as a picture, shared from the app through a prepared
message or sent as a photo to the chat with the bot."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe, SavePreparedInlineMessage, SendPhoto
from sqlalchemy import func, select

from assistant.core.i18n import Translator
from assistant.core.models import ShareCard
from assistant.core.services import forecast_cards
from assistant.core.services.forecast_cards import ForecastCard
from tests.stubs import forecast_payload

SITE = "https://app.example"
MOSCOW = (55.75204, 37.61781)  # the home city of a new user
TULA = {
    "name": "Тула",
    "admin": "Тульская область",
    "country": "Россия",
    "lat": 54.19,
    "lon": 37.62,
    "timezone": "Europe/Moscow",
    "geo_id": 480562,
}


@pytest.fixture
def places(meteo, monkeypatch) -> list[tuple[float, float]]:
    """The places the API asks Open-Meteo about, in order."""
    asked: list[tuple[float, float]] = []
    forecast = meteo.forecast

    async def recorded(lat: float, lon: float, **options: Any) -> dict[str, Any]:
        asked.append((lat, lon))
        return await forecast(lat, lon, **options)

    monkeypatch.setattr(meteo, "forecast", recorded)
    return asked


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[ForecastCard]:
    """The pictures drawn, in order; each is drawn for real."""
    cards: list[ForecastCard] = []
    draw = forecast_cards.draw_card

    async def draw_and_keep(card: ForecastCard, t: Translator) -> bytes:
        cards.append(card)
        return await draw(card, t)

    monkeypatch.setattr(forecast_cards, "draw_card", draw_and_keep)
    return cards


async def _pictures(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(ShareCard)))


def _refused(response, status: int, service: str | None = None) -> bool:
    body = response.json()
    return (response.status_code, body.get("service")) == (status, service)


async def test_the_home_citys_week_is_shared_by_a_link(
    client, auth, telegram, meteo, places, drawn, session
) -> None:
    shared = await client.post("/api/weather/share", headers=auth())
    assert shared.status_code == 200
    assert shared.json() == {"prepared_id": "prepared-1"}
    [prepared] = telegram.of(SavePreparedInlineMessage)
    assert prepared.user_id == 1
    assert prepared.allow_user_chats and prepared.allow_group_chats and prepared.allow_channel_chats
    assert prepared.result.caption == "🌤 Москва: погода на неделю"
    link = prepared.result.photo_url
    assert link.startswith(f"{SITE}/api/share/") and link.endswith(".jpg")
    assert prepared.result.thumbnail_url == link
    # Telegram downloads the picture without anyone's signature.
    picture = await client.get(link.removeprefix(SITE))
    assert picture.status_code == 200 and picture.content[:2] == b"\xff\xd8"
    [card] = drawn
    assert (card.city, card.today, len(card.days), card.bot) == (
        "Москва",
        date(2026, 9, 28),
        7,
        "assistant_bot",
    )
    assert places == [MOSCOW] and meteo.user_ids == [1]  # on the user's own budget
    [kept] = (await session.scalars(select(ShareCard))).all()
    assert kept.habit_id is None


async def test_the_week_can_be_sent_to_the_bot_chat(client, auth, telegram, places) -> None:
    sent = await client.post("/api/weather/card?city=0", headers=auth())
    assert sent.status_code == 204
    [photo] = telegram.of(SendPhoto)
    assert photo.chat_id == 1
    assert photo.caption == "🌤 Москва: погода на неделю"
    assert photo.photo.filename == "forecast.jpg"
    assert photo.photo.data[:2] == b"\xff\xd8"
    assert places == [MOSCOW]


async def test_an_extra_citys_week(client, auth, telegram, places) -> None:
    city = (await client.post("/api/me/cities", json=TULA, headers=auth())).json()
    shared = await client.post(f"/api/weather/share?city={city['id']}", headers=auth())
    sent = await client.post(f"/api/weather/card?city={city['id']}", headers=auth())
    assert (shared.status_code, sent.status_code) == (200, 204)
    [prepared] = telegram.of(SavePreparedInlineMessage)
    [photo] = telegram.of(SendPhoto)
    assert prepared.result.caption == photo.caption == "🌤 Тула: погода на неделю"
    assert places == [(54.19, 37.62)] * 2


async def test_the_picture_speaks_the_users_language(client, auth, telegram) -> None:
    await client.post("/api/weather/card", headers=auth(lang="en"))
    [photo] = telegram.of(SendPhoto)
    assert photo.caption == "🌤 Москва: the week's weather"


async def test_just_after_midnight_the_week_has_six_days(client, auth, clock, drawn) -> None:
    clock[0] = datetime(2026, 9, 28, 21, 30, tzinfo=UTC)  # 00:30 of the 29th in Moscow
    sent = await client.post("/api/weather/card", headers=auth(signed_at=clock[0]))
    assert sent.status_code == 204
    [card] = drawn
    assert (card.today, len(card.days)) == (date(2026, 9, 29), 6)


async def test_a_foreign_or_deleted_city_is_404_and_spends_nothing(
    app, client, auth, meteo, telegram
) -> None:
    foreign = (await client.post("/api/me/cities", json=TULA, headers=auth(2))).json()
    mine = (await client.post("/api/me/cities", json=TULA, headers=auth(1))).json()
    await client.delete(f"/api/me/cities/{mine['id']}", headers=auth(1))
    for city_id in (foreign["id"], mine["id"], 2**63 - 1):
        for path in ("share", "card"):
            response = await client.post(f"/api/weather/{path}?city={city_id}", headers=auth())
            assert response.status_code == 404
            assert (response.json()["code"], response.json()["entity"]) == ("not_found", "city")
    assert meteo.user_ids == [] and telegram.calls == []
    # Nor did any take a place among the six pictures a minute.
    assert [app.state.assistant.cards.check(1) for _ in range(6)] == [None] * 6


@pytest.mark.parametrize("path", ["share", "card"])
@pytest.mark.parametrize("city", ["-1", str(2**63), "home"])
async def test_a_city_that_is_not_an_id_is_422(client, auth, path, city) -> None:
    response = await client.post(f"/api/weather/{path}?city={city}", headers=auth())
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["field"]) == ("validation_error", "city")


async def test_six_pictures_a_minute_with_the_habit_cards(client, auth, meteo, monotonic) -> None:
    habit = (await client.post("/api/habits", json={"name": "Спорт"}, headers=auth())).json()
    for path in ("/api/weather/share", "/api/weather/card", f"/api/habits/{habit['id']}/card") * 2:
        assert (await client.post(path, headers=auth())).status_code in (200, 204)
    for path in ("share", "card"):
        refused = await client.post(f"/api/weather/{path}", headers=auth())
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) == 60
    assert meteo.user_ids == [1] * 4  # a refused picture asks for no forecast
    monotonic[0] += 60
    assert (await client.post("/api/weather/share", headers=auth())).status_code == 200


async def test_without_the_forecast_it_is_503_of_open_meteo(
    client, auth, meteo, telegram, session
) -> None:
    meteo.fail = True
    for path in ("share", "card"):
        response = await client.post(f"/api/weather/{path}", headers=auth())
        assert _refused(response, 503, "open-meteo")
        assert response.json()["code"] == "upstream_unavailable"
    assert telegram.calls == [] and await _pictures(session) == 0


async def test_a_forecast_without_days_is_503_of_open_meteo(
    client, auth, meteo, telegram, session
) -> None:
    meteo.forecast_data = forecast_payload(days=0)
    for path in ("share", "card"):
        response = await client.post(f"/api/weather/{path}", headers=auth())
        assert _refused(response, 503, "open-meteo")
    assert telegram.of(SavePreparedInlineMessage) == [] and telegram.of(SendPhoto) == []
    assert await _pictures(session) == 0


async def test_an_unreachable_telegram_is_503_and_keeps_no_picture(
    client, auth, telegram, session
) -> None:
    for path in ("share", "card"):  # the bot's name for the picture is asked first
        telegram.errors.append(TelegramNetworkError(method=GetMe(), message="timeout"))
        assert _refused(await client.post(f"/api/weather/{path}", headers=auth()), 503, "telegram")
    assert await _pictures(session) == 0
    # The bot's name is kept once asked: the next failure is the message's, then the photo's.
    assert (await client.post("/api/weather/share", headers=auth())).status_code == 200
    assert await _pictures(session) == 1
    for path in ("share", "card"):
        telegram.errors.append(TelegramNetworkError(method=GetMe(), message="timeout"))
        assert _refused(await client.post(f"/api/weather/{path}", headers=auth()), 503, "telegram")
    assert await _pictures(session) == 1  # the picture of the failed message is forgotten


async def test_without_the_bot_or_the_site_it_is_503_and_spends_nothing(
    app, client, auth, meteo, telegram
) -> None:
    state = app.state.assistant
    bot, site = state.bot, state.site
    state.site = None  # the bot can still send the picture to the chat: the app goes there
    off = await client.post("/api/weather/share", headers=auth())
    assert _refused(off, 503, "telegram")
    state.bot = None
    for path in ("share", "card"):
        assert _refused(await client.post(f"/api/weather/{path}", headers=auth()), 503, "telegram")
    # Neither a request to Open-Meteo nor a place among the six pictures a minute.
    assert meteo.user_ids == [] and telegram.calls == []
    assert [state.cards.check(1) for _ in range(6)] == [None] * 6
    state.bot, state.site = bot, site
