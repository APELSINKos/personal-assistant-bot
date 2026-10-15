"""«🖼 Картинка» under «📅 Неделя»: the week's forecast as a photo in the chat."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date, datetime
from typing import Any

import httpx
import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendMessage, SendPhoto
from aiogram.types import Update
from aiogram.types import User as TgUser

from assistant.bot.keyboards import WeatherCardCb, WeatherCb
from assistant.bot.routers import weather as weather_router
from assistant.core.clients.openmeteo import FORECAST_TTL, City, OpenMeteoClient
from assistant.core.i18n import Translator
from assistant.core.services import cities, forecast_cards
from assistant.core.services.forecast_cards import ForecastCard
from tests.bot.fakes import callback_update
from tests.stubs import FORECAST_NOW, forecast_payload

BOT = TgUser(id=99, is_bot=True, first_name="Помощник", username="assistant_bot")
MOSCOW = (55.75, 37.62)  # the home city the bot gives a new user, as Open-Meteo is asked for it
OMSK = City(
    name="Омск",
    admin="Омская область",
    country="Россия",
    lat=54.99,
    lon=73.37,
    timezone="Asia/Omsk",
    geo_id=1496153,
)
TULA = City(
    name="Тула",
    admin="Тульская область",
    country="Россия",
    lat=54.19,
    lon=37.62,
    timezone="Europe/Moscow",
    geo_id=480562,
)
GONE = "Этого города уже нет в списке"
UNAVAILABLE = "⚠️ Не удалось получить погоду. Попробуй чуть позже."
NO_DAYS = "Прогноза на неделю сейчас нет."
STALE = "Эта кнопка устарела — открой раздел заново из меню."


class OpenMeteo:
    """Open-Meteo behind the bot's real client: the stub's forecast for any place but those given
    one of their own in `places`; `asked` holds the place of every request that reached it."""

    def __init__(self) -> None:
        self.places: dict[tuple[float, float], dict[str, Any]] = {}
        self.asked: list[tuple[float, float]] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        place = (float(params["latitude"]), float(params["longitude"]))
        self.asked.append(place)
        if self.down:
            return httpx.Response(503)
        return httpx.Response(200, json=self.places.get(place, forecast_payload()))


class Meteo(OpenMeteoClient):
    """The bot's client with its cache and budgets, noting whose forecast each call was."""

    def __init__(self, http: httpx.AsyncClient, clock: Callable[[], float]) -> None:
        super().__init__(http, clock=clock)
        self.user_ids: list[int | None] = []

    async def forecast(
        self, lat: float, lon: float, *, user_id: int | None = None
    ) -> dict[str, Any]:
        self.user_ids.append(user_id)
        return await super().forecast(lat, lon, user_id=user_id)


@pytest.fixture
def server() -> OpenMeteo:
    return OpenMeteo()


@pytest.fixture
async def meteo(server: OpenMeteo, monotonic: list[float]) -> AsyncIterator[Meteo]:
    """The real client instead of the stub, on the clock the tests move by hand: whether a
    picture costs a request is the cache's to say."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as http:
        yield Meteo(http, lambda: monotonic[0])


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch, fake) -> None:
    """The weather's clock at 10:00 in Moscow, when the stub forecast was made; the bot's name."""
    monkeypatch.setattr(weather_router, "clock", lambda: FORECAST_NOW)
    fake.results[GetMe] = BOT


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[ForecastCard]:
    """The cards drawn, in order; each is drawn for real."""
    cards: list[ForecastCard] = []
    draw = forecast_cards.draw_card

    async def draw_and_keep(card: ForecastCard, t: Translator) -> bytes:
        cards.append(card)
        return await draw(card, t)

    monkeypatch.setattr(forecast_cards, "draw_card", draw_and_keep)
    return cards


def packed(message) -> list[list[str]]:
    return [
        [button.callback_data for button in row] for row in message.reply_markup.inline_keyboard
    ]


def press(city: int = 0, lang: str = "ru") -> Update:
    """«🖼 Картинка» of the home city, or of an extra one."""
    return callback_update(WeatherCardCb(city=city).pack(), lang=lang)


async def test_the_week_comes_as_a_photo_from_the_forecast_just_shown(
    feed, fake, server, meteo, drawn
) -> None:
    await feed(callback_update(WeatherCb(view="week").pack()))
    week = fake.of(EditMessageText)[-1]
    picture = week.reply_markup.inline_keyboard[0][2]
    assert (picture.text, picture.callback_data) == ("🖼 Картинка", "wc:0")
    await feed(callback_update(picture.callback_data))
    [photo] = fake.of(SendPhoto)
    assert photo.chat_id == 1
    assert photo.caption == "🌤 Москва: погода на неделю"
    assert photo.photo.filename == "forecast.jpg"
    assert photo.photo.data[:2] == b"\xff\xd8"  # a JPEG
    [card] = drawn
    assert (card.city, card.today, card.bot) == ("Москва", date(2026, 9, 28), "assistant_bot")
    assert (len(card.days), card.days[-1].day) == (7, date(2026, 10, 4))
    # The forecast the week was drawn from, kept by the client: no request of its own.
    assert server.asked == [MOSCOW] and meteo.user_ids == [1, 1]
    assert [answer.text for answer in fake.of(AnswerCallbackQuery)] == [None, None]
    assert fake.of(EditMessageText) == [week]  # the week stays as it is
    assert fake.of(SendMessage) == []


async def test_only_a_forecast_not_kept_costs_a_request(
    feed, fake, server, meteo, monotonic
) -> None:
    await feed(press())  # nothing kept yet
    await feed(press())
    assert server.asked == [MOSCOW]
    monotonic[0] += FORECAST_TTL  # ten minutes on: the kept forecast is too old
    await feed(press())
    assert server.asked == [MOSCOW, MOSCOW]
    assert meteo.user_ids == [1, 1, 1]  # on the budget of the user who asked
    assert len(fake.of(SendPhoto)) == 3


async def test_an_extra_citys_button_draws_that_city(
    feed, fake, session, make_user, server, drawn
) -> None:
    user = await make_user()
    await cities.add(session, user, OMSK)
    await session.commit()
    [omsk] = await cities.list_for(session, 1)
    server.places[(OMSK.lat, OMSK.lon)] = forecast_payload(zone="Asia/Omsk")  # 13:00 there
    await feed(callback_update(WeatherCb(view="week", city=omsk.id).pack()))
    week = fake.of(EditMessageText)[-1]
    assert week.text.startswith("📅 Омск — 7 дней\n")
    assert packed(week)[0][2] == WeatherCardCb(city=omsk.id).pack()
    await feed(callback_update(packed(week)[0][2]))
    assert fake.of(SendPhoto)[-1].caption == "🌤 Омск: погода на неделю"
    [card] = drawn
    assert (card.city, card.at) == ("Омск", datetime(2026, 9, 28, 13, 0))
    assert server.asked == [(OMSK.lat, OMSK.lon)]  # the week's forecast, kept


async def test_a_gone_or_strange_city_sends_nothing(
    feed, fake, session, make_user, meteo, card_budget
) -> None:
    user = await make_user()
    gone = (await cities.add(session, user, TULA)).id
    neighbour = await make_user(id=2)
    theirs = (await cities.add(session, neighbour, OMSK)).id
    await session.commit()
    await cities.delete(session, 1, gone)  # meanwhile in the app
    await session.commit()
    for city in (gone, theirs):
        await feed(press(city))
        assert fake.of(AnswerCallbackQuery)[-1].text == GONE
    assert fake.of(SendPhoto) == [] and meteo.user_ids == []
    # Nor did either take a place among the six pictures a minute.
    assert [card_budget.check(1) for _ in range(6)] == [None] * 6


async def test_six_pictures_a_minute_with_the_cards_reports_and_rates(
    feed, fake, meteo, card_budget, monotonic
) -> None:
    for _ in range(4):  # four other pictures a moment ago: the limit is one for all of them
        assert card_budget.check(1) is None
    for _ in range(3):
        await feed(press())
    refused = fake.of(AnswerCallbackQuery)[-1]
    assert refused.show_alert
    assert refused.text == "⏳ Слишком много картинок подряд — попробуй через 60 с."
    assert len(fake.of(SendPhoto)) == 2
    assert meteo.user_ids == [1, 1]  # the refused press asked for no forecast
    monotonic[0] += 60
    await feed(press())
    assert len(fake.of(SendPhoto)) == 3


async def test_without_the_forecast_nothing_is_sent(feed, fake, server) -> None:
    server.down = True
    await feed(press())
    assert fake.of(AnswerCallbackQuery)[-1].text == UNAVAILABLE
    assert fake.of(SendPhoto) == [] and fake.sent_texts() == []


async def test_a_forecast_without_days_sends_nothing(feed, fake, server) -> None:
    server.places[MOSCOW] = forecast_payload(days=0)
    await feed(press())
    assert fake.of(AnswerCallbackQuery)[-1].text == NO_DAYS
    assert fake.of(SendPhoto) == [] and fake.sent_texts() == []


async def test_a_forged_picture_button_is_stale(feed, fake, meteo) -> None:
    for data in ("wc:-1", "wc:x", "wc:9223372036854775808", "wc:0:0", "wc"):
        await feed(callback_update(data))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE, data
    assert fake.of(SendPhoto) == [] and meteo.user_ids == []
    # The longest a real one gets, well within Telegram's 64 bytes.
    assert WeatherCardCb(city=2**63 - 1).pack() == "wc:9223372036854775807"


async def test_the_picture_in_english(feed, fake) -> None:
    await feed(press(lang="en"))
    assert fake.of(SendPhoto)[-1].caption == "🌤 Москва: the week's weather"
