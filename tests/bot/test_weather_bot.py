from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from assistant.bot.keyboards import CityCb, WeatherCb, weather_views
from assistant.bot.routers import weather as weather_router
from assistant.core.clients.openmeteo import City
from assistant.core.i18n import translator
from assistant.core.models import User
from assistant.core.services import cities
from tests.bot.fakes import callback_update, message_update
from tests.stubs import FORECAST_NOW, StubMeteo, forecast_payload

TULA = City(
    name="Тула",
    admin="Тульская область",
    country="Россия",
    lat=54.19,
    lon=37.62,
    timezone="Europe/Moscow",
    geo_id=480562,
)
OMSK = replace(TULA, name="Омск", lat=54.99, lon=73.37, timezone="Asia/Omsk", geo_id=1496153)
KAMCHATKA = replace(
    TULA,
    name="Петропавловск-Камчатский",
    lat=53.04,
    lon=158.65,
    timezone="Asia/Kamchatka",
    geo_id=2122104,
)
SOCHI = replace(TULA, name="Сочи", lat=43.6, lon=39.73, geo_id=491422)
NOW_TEXT = (
    "🌤 Москва: +10°C, малооблачно\n"
    "Ощущается как +7°C, ветер 3 м/с\n"
    "Сегодня: +6…+13°C\n"
    "\n"
    "🚲 Сегодня хороший день для велосипеда\n"
    "\n"
    "Данные о погоде: open-meteo.com"
)
UNAVAILABLE = "⚠️ Не удалось получить погоду. Попробуй чуть позже."
GONE = "Этого города уже нет в списке"
STALE = "Эта кнопка устарела — открой раздел заново из меню."


class Places(StubMeteo):
    """The stub's forecast for any place but those given one of their own in `places`."""

    def __init__(self) -> None:
        super().__init__()
        self.places: dict[tuple[float, float], dict[str, Any]] = {}
        self.asked: list[tuple[float, float]] = []

    async def forecast(self, lat: float, lon: float, **options: Any) -> dict[str, Any]:
        self.asked.append((lat, lon))
        anywhere = await super().forecast(lat, lon, **options)  # fails as the stub does
        return self.places.get((lat, lon), anywhere)


@pytest.fixture
def meteo() -> Places:
    return Places()


@pytest.fixture(autouse=True)
def now(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """The weather's clock: when the stub forecast was asked for (10:00 in Moscow) unless a test
    moves it."""
    moment = [FORECAST_NOW]
    monkeypatch.setattr(weather_router, "clock", lambda: moment[0])
    return moment


def buttons(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.inline_keyboard]


def packed(message) -> list[list[str]]:
    return [
        [button.callback_data for button in row] for row in message.reply_markup.inline_keyboard
    ]


async def keep(session, make_user, *places: City) -> User:
    """The user with these extra cities, added as the app adds them."""
    user = await make_user()
    for place in places:
        await cities.add(session, user, place)
    await session.commit()
    return user


async def test_the_weather_now_with_its_buttons(feed, fake, meteo) -> None:
    await feed(message_update("🌤 Погода"))
    [sent] = fake.of(SendMessage)
    assert sent.text == NOW_TEXT
    assert meteo.user_ids == [1]  # the forecast spent the budget of the user who asked
    assert sent.link_preview_options.is_disabled  # open-meteo.com without a preview card
    assert buttons(sent) == [["🕐 По часам", "📅 Неделя"], ["🏙 Города"]]
    assert packed(sent) == [
        [WeatherCb(view="hours").pack(), WeatherCb(view="week").pack()],
        [CityCb(action="list", back="w").pack()],
    ]


async def test_the_views_change_the_message_itself(feed, fake) -> None:
    await feed(callback_update(WeatherCb(view="hours").pack()))
    hours = fake.of(EditMessageText)[-1]
    lines = hours.text.split("\n")
    assert lines[:3] == ["🕐 Москва — по часам", "", "11:00 🌤 +11°C"]  # from the next hour
    assert lines[-3:] == ["22:00 🌙 +8°C", "", "Данные о погоде: open-meteo.com"]
    assert hours.link_preview_options.is_disabled
    assert buttons(hours) == [["🌤 Сейчас", "📅 Неделя"], ["🏙 Города"]]
    assert packed(hours)[0] == [WeatherCb(view="now").pack(), WeatherCb(view="week").pack()]
    await feed(callback_update(WeatherCb(view="week").pack()))
    week = fake.of(EditMessageText)[-1]
    assert week.text.startswith("📅 Москва — 7 дней\n\nСегодня 🌤 +6…+13°C\nЗавтра 🌤 +6…+13°C\n")
    assert week.link_preview_options.is_disabled
    assert buttons(week) == [["🌤 Сейчас", "🕐 По часам"], ["🏙 Города"]]
    await feed(callback_update(WeatherCb(view="now").pack()))
    assert fake.of(EditMessageText)[-1].text == NOW_TEXT
    assert buttons(fake.of(EditMessageText)[-1])[0] == ["🕐 По часам", "📅 Неделя"]
    assert fake.of(SendMessage) == []
    assert [answer.text for answer in fake.of(AnswerCallbackQuery)] == [None, None, None]


async def test_the_hours_start_after_the_clock_of_the_bot(feed, fake, now) -> None:
    now[0] = datetime(2026, 9, 28, 20, 30, tzinfo=UTC)  # 23:30 in Moscow
    await feed(callback_update(WeatherCb(view="hours").pack()))
    lines = fake.of(EditMessageText)[-1].text.split("\n")
    assert lines[2:4] == ["Завтра, 29 сентября", "00:00 🌙 +7°C"]


async def test_the_views_in_english(feed, fake) -> None:
    await feed(message_update("🌤 Weather", lang="en"))
    sent = fake.of(SendMessage)[-1]
    assert sent.text.endswith("\n\nWeather data: open-meteo.com")
    assert buttons(sent) == [["🕐 Hourly", "📅 Week"], ["🏙 Cities"]]
    await feed(callback_update(WeatherCb(view="week").pack(), lang="en"))
    week = fake.of(EditMessageText)[-1]
    assert week.text.startswith("📅 Москва — 7 days\n\nToday 🌤 +6…+13°C\n")
    assert buttons(week)[0] == ["🌤 Now", "🕐 Hourly"]


async def test_a_city_button_shows_the_same_view_of_that_city(
    feed, fake, meteo, session, make_user
) -> None:
    await keep(session, make_user, TULA, OMSK, KAMCHATKA)
    [tula, omsk, kamchatka] = await cities.list_for(session, 1)
    meteo.places[(OMSK.lat, OMSK.lon)] = forecast_payload(zone="Asia/Omsk")  # 13:00 there
    await feed(message_update("🌤 Погода"))
    sent = fake.of(SendMessage)[-1]
    assert buttons(sent) == [
        ["🕐 По часам", "📅 Неделя"],
        ["🏠 Москва", "Тула", "Омск"],
        ["Петропавловск-Камча…"],
        ["🏙 Города"],
    ]
    assert packed(sent)[1:3] == [
        [
            WeatherCb(view="now").pack(),
            WeatherCb(view="now", city=tula.id).pack(),
            WeatherCb(view="now", city=omsk.id).pack(),
        ],
        [WeatherCb(view="now", city=kamchatka.id).pack()],
    ]
    await feed(callback_update(WeatherCb(view="hours").pack()))
    hours = fake.of(EditMessageText)[-1]
    assert packed(hours)[1][2] == WeatherCb(view="hours", city=omsk.id).pack()  # keeps the view
    await feed(callback_update(packed(hours)[1][2]))
    view = fake.of(EditMessageText)[-1]
    assert meteo.asked[-1] == (54.99, 73.37) and meteo.user_ids[-1] == 1
    assert view.text.split("\n")[:3] == ["🕐 Омск — по часам (местное время)", "", "14:00 🌤 +13°C"]
    assert packed(view)[0] == [
        WeatherCb(view="now", city=omsk.id).pack(),
        WeatherCb(view="week", city=omsk.id).pack(),
    ]
    # Every city, the one shown included, and the cities' sub-view.
    assert buttons(view)[1:] == [
        ["🏠 Москва", "Тула", "Омск"],
        ["Петропавловск-Камча…"],
        ["🏙 Города"],
    ]
    await feed(callback_update(packed(view)[0][0]))
    assert fake.of(EditMessageText)[-1].text.startswith("🌤 Омск: +10°C, малооблачно\n")
    await feed(callback_update(packed(view)[1][0]))  # home: Moscow's hours again
    assert fake.of(EditMessageText)[-1].text.startswith("🕐 Москва — по часам\n")
    assert fake.of(SendMessage) == [sent]


async def test_long_names_are_cut_in_the_buttons(feed, fake, session, make_user) -> None:
    home = "Петропавловск-Камчатский"
    user = await make_user(tz="Asia/Kamchatka", city=home, lat=53.04, lon=158.65)
    await cities.add(session, user, TULA)
    await session.commit()
    await feed(message_update("🌤 Погода"))
    assert buttons(fake.of(SendMessage)[-1])[1] == ["🏠 Петропавловск-Камча…", "Тула"]
    # The longest value a weather button gets, well within Telegram's 64 bytes.
    assert WeatherCb(view="hours", city=2**63 - 1, new=1).pack() == "w:hours:9223372036854775807:1"


async def test_a_gone_city_shows_the_home_city_instead(feed, fake, session, make_user) -> None:
    await keep(session, make_user, TULA)
    other = await make_user(id=2)
    theirs = await cities.add(session, other, SOCHI)
    [tula] = await cities.list_for(session, 1)
    await cities.delete(session, 1, tula.id)  # meanwhile in the app
    await session.commit()
    for city in (tula.id, theirs.id):
        await feed(callback_update(WeatherCb(view="week", city=city).pack()))
        assert fake.of(AnswerCallbackQuery)[-1].text == GONE
        view = fake.of(EditMessageText)[-1]
        assert view.text.startswith("📅 Москва — 7 дней\n")
        assert buttons(view) == [["🌤 Сейчас", "🕐 По часам"], ["🏙 Города"]]
    assert [city.name for city in await cities.list_for(session, 2)] == ["Сочи"]


async def test_without_the_forecast_nothing_changes(feed, fake, meteo) -> None:
    meteo.fail = True
    for data in (WeatherCb(view="hours"), WeatherCb(view="week", new=1)):
        await feed(callback_update(data.pack()))
        assert fake.of(AnswerCallbackQuery)[-1].text == UNAVAILABLE
    assert fake.of(EditMessageText) == [] and fake.of(SendMessage) == []


async def test_a_button_under_the_digest_sends_the_view_apart(feed, fake) -> None:
    digest_row = weather_views(translator("ru"), "now", new=1)  # under the digest, «Мой день»
    assert [button.text for button in digest_row] == ["🕐 По часам", "📅 Неделя"]
    await feed(callback_update(digest_row[0].callback_data))
    assert fake.of(EditMessageText) == []  # the digest stays whole
    [sent] = fake.of(SendMessage)
    assert sent.text.startswith("🕐 Москва — по часам\n")
    assert sent.link_preview_options.is_disabled
    # The usual buttons: they change the new message in place.
    assert packed(sent)[0] == [WeatherCb(view="now").pack(), WeatherCb(view="week").pack()]
    assert fake.of(AnswerCallbackQuery)[-1].text is None


async def test_a_gone_city_under_the_digest_sends_the_home_city(
    feed, fake, session, make_user
) -> None:
    await keep(session, make_user, TULA)
    [tula] = await cities.list_for(session, 1)
    await cities.delete(session, 1, tula.id)
    await session.commit()
    await feed(callback_update(WeatherCb(view="now", city=tula.id, new=1).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == GONE
    assert fake.of(SendMessage)[-1].text == NOW_TEXT
    assert fake.of(EditMessageText) == []


async def test_back_from_the_cities_is_the_weather_now(feed, fake, meteo) -> None:
    await feed(message_update("🌤 Погода"))
    await feed(callback_update(packed(fake.of(SendMessage)[-1])[-1][0]))  # «🏙 Города»
    sub_view = fake.of(EditMessageText)[-1]
    assert sub_view.text.startswith("🏙 Города\n")
    back = sub_view.reply_markup.inline_keyboard[-1][0]
    assert (back.text, back.callback_data) == ("↩️ Назад", WeatherCb(view="now").pack())
    meteo.fail = True
    await feed(callback_update(back.callback_data))
    assert fake.of(AnswerCallbackQuery)[-1].text == UNAVAILABLE
    assert fake.of(EditMessageText) == [sub_view]  # the sub-view stays
    meteo.fail = False
    await feed(callback_update(back.callback_data))
    assert fake.of(EditMessageText)[-1].text == NOW_TEXT


async def test_a_forged_weather_button_is_stale(feed, fake) -> None:
    for data in ("w:month:0:0", "w:hours:-1:0", "w:hours:x:0", "w:hours:0:x", "w:" + "h" * 60):
        await feed(callback_update(data))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    assert fake.sent_texts() == []
