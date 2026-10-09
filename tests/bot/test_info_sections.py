from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from assistant.bot.keyboards import CityCb, MoneyCb, RatesCb, WeatherCb
from assistant.bot.routers import today as today_router
from assistant.bot.routers import weather as weather_router
from assistant.core.services import notes
from tests.bot.fakes import callback_update, message_update
from tests.stubs import FORECAST_NOW

NBSP = " "
MY_DAY = (
    "🌅 Доброе утро, Alex!\n"
    "📅 Сегодня, 28 сентября, понедельник\n"
    "\n"
    "🌤 Москва: +10°C, малооблачно\n"
    "🚲 Сегодня хороший день для велосипеда\n"
    "\n"
    "📌 На сегодня напоминаний нет\n"
    "🎯 Привычек пока нет\n"
    "📝 Заметок: 0\n"
    "💵 84,20 ₽ · 💶 96,67 ₽"
)
APP = "https://app.example/miniapp/"


@pytest.fixture(autouse=True)
def now(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """The clock of «Мой день» and of the weather: when the stub forecast was asked for (10:00
    in Moscow) unless a test moves it."""
    moment = [FORECAST_NOW]
    monkeypatch.setattr(today_router, "clock", lambda: moment[0])
    monkeypatch.setattr(weather_router, "clock", lambda: moment[0])
    return moment


def buttons(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.inline_keyboard]


async def test_weather(feed, fake) -> None:
    await feed(message_update("🌤 Погода"))
    [reply] = fake.of(SendMessage)
    assert reply.text.startswith("🌤 Москва: +10°C, малооблачно")
    assert reply.text.endswith("\n\n🚲 Сегодня хороший день для велосипеда")
    button = reply.reply_markup.inline_keyboard[-1][0]
    assert button.text == "🏙 Города"
    assert CityCb.unpack(button.callback_data) == CityCb(action="list", back="w")


async def test_weather_unavailable(feed, fake, meteo) -> None:
    meteo.fail = True
    await feed(message_update("🌤 Weather", lang="en"))
    assert fake.sent_texts() == ["⚠️ Couldn't get the weather. Please try again a bit later."]


async def test_today(feed, fake) -> None:
    await feed(message_update("📅 Мой день"))
    [sent] = fake.of(SendMessage)
    assert sent.text == MY_DAY
    assert sent.link_preview_options.is_disabled  # no card of an address in a reminder or a note
    # The home city's hours and week, each as a message of its own.
    assert buttons(sent) == [["🕐 По часам", "📅 Неделя"]]
    assert [button.callback_data for button in sent.reply_markup.inline_keyboard[0]] == [
        WeatherCb(view="hours", new=1).pack(),
        WeatherCb(view="week", new=1).pack(),
    ]


async def test_today_with_the_app(feed, fake, settings) -> None:
    settings.webapp_url = APP
    await feed(message_update("📅 My day", lang="en"))
    sent = fake.of(SendMessage)[-1]
    assert buttons(sent) == [["🕐 Hourly", "📅 Week"], ["📱 Open the app"]]
    assert sent.reply_markup.inline_keyboard[1][0].web_app.url == APP


async def test_today_survives_upstream_failures(feed, fake, meteo, cbr, settings) -> None:
    meteo.fail = cbr.fail = True
    await feed(message_update("📅 Мой день"))
    [sent] = fake.of(SendMessage)
    assert "🌤 Погода временно недоступна" in sent.text and "💵" not in sent.text
    # Without the weather no buttons of the forecast.
    assert sent.reply_markup is None
    assert sent.link_preview_options.is_disabled
    settings.webapp_url = APP
    await feed(message_update("📅 Мой день"))
    assert buttons(fake.of(SendMessage)[-1]) == [["📱 Открыть приложение"]]


async def test_my_day_in_the_evening(feed, fake, now, session, make_user) -> None:
    user = await make_user()
    wifi = await notes.create(session, user.id, "Пароль от wifi:\nhunter2", now=FORECAST_NOW)
    await notes.create(session, user.id, "Покупки", ["молоко", "хлеб"], now=FORECAST_NOW)
    shopping = await notes.create(session, user.id, "Ещё покупки", ["сыр"], now=FORECAST_NOW)
    await notes.set_item(session, user.id, shopping.id, shopping.items[0].id, True)
    await notes.set_pinned(session, user.id, shopping.id, True, FORECAST_NOW)
    await notes.set_pinned(session, user.id, wifi.id, True, FORECAST_NOW + timedelta(minutes=1))
    await session.commit()
    now[0] = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)  # 17:00 in Moscow
    await feed(message_update("📅 Мой день"))
    lines = fake.of(SendMessage)[-1].text.split("\n")
    assert lines[0] == "🌆 Добрый вечер, Alex!"
    assert lines[3:7] == [
        "🌤 Москва: +10°C, малооблачно",
        "🚲 Сегодня хороший день для велосипеда",
        "Завтра: 🌤 +6…+13°C",
        "",
    ]
    # The pinned ones under the count, the last pinned first.
    assert lines[-4:-1] == ["📝 Заметок: 3", "📌 Пароль от wifi: hunter2", "📌 Ещё покупки ✅ 1/1"]


async def test_the_forecast_under_my_day_comes_as_a_message_of_its_own(feed, fake) -> None:
    await feed(message_update("📅 Мой день"))
    day = fake.of(SendMessage)[-1]
    await feed(callback_update(day.reply_markup.inline_keyboard[0][1].callback_data))
    assert fake.of(EditMessageText) == []  # «Мой день» stays as it is
    week = fake.of(SendMessage)[-1]
    assert week is not day and week.text.startswith("📅 Москва — 7 дней\n\nСегодня 🌤 +6…+13°C\n")
    assert buttons(week)[0] == ["🌤 Сейчас", "🕐 По часам", "🖼 Картинка"]


async def test_rates_and_converter(feed, fake) -> None:
    await feed(callback_update(MoneyCb(action="rates").pack()))  # «💰 Финансы» → «💱 Курсы»
    assert fake.sent_texts()[0].startswith("💱 Курс ЦБ РФ на 28 сентября")
    await feed(callback_update(RatesCb(source="USD", target="RUB").pack()))
    assert fake.sent_texts()[-1] == "Сколько USD перевести в RUB?"
    await feed(message_update(None, sticker=True))
    assert fake.sent_texts()[-1] == "Нужен текст. Напиши сумму числом, например 100 или 99,5."
    for bad in ("nan", "0", "-5", "1e10", "abc"):
        await feed(message_update(bad))
        assert fake.sent_texts()[-1].startswith("Нужно число больше нуля")
    await feed(message_update("100"))
    assert fake.sent_texts()[-1] == f"💱 100,00 USD = 8{NBSP}419,75 RUB"
    await feed(message_update("сто"))  # the dialog is over
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_converter_clears_state_when_rates_fail_at_conversion_time(feed, fake, cbr) -> None:
    await feed(callback_update(RatesCb(source="USD", target="RUB").pack()))
    cbr.fail = True
    await feed(message_update("100"))
    assert fake.sent_texts()[-1] == "⚠️ Не удалось получить курсы. Попробуй чуть позже."
    await feed(message_update("сто"))  # the dialog is over: state was cleared, not stuck
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_converter_rejects_forged_pair(feed, fake) -> None:
    await feed(callback_update(RatesCb(source="RUB", target="RUB").pack()))
    [answer] = fake.of(AnswerCallbackQuery)
    assert answer.text == "Эта кнопка устарела — открой раздел заново из меню."
    assert fake.of(SendMessage) == []


async def test_rates_unavailable(feed, fake, cbr) -> None:
    cbr.fail = True
    await feed(callback_update(MoneyCb(action="rates").pack()))
    assert fake.sent_texts() == ["⚠️ Не удалось получить курсы. Попробуй чуть позже."]
