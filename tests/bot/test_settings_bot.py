from __future__ import annotations

from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import ReplyKeyboardMarkup

from assistant.bot.keyboards import SettingsCb
from assistant.core.clients.openmeteo import City
from assistant.core.models import User
from tests.bot.fakes import callback_update, message_update

SPB = City(
    name="Санкт-Петербург",
    admin="Санкт-Петербург",
    country="Россия",
    lat=59.94,
    lon=30.31,
    timezone="Europe/Moscow",
)
SPB_US = City(
    name="Saint Petersburg",
    admin="Florida",
    country="США",
    lat=27.77,
    lon=-82.68,
    timezone="America/New_York",
)


async def test_settings_view_and_toggle(feed, fake) -> None:
    await feed(message_update("/settings"))
    assert fake.sent_texts()[-1] == (
        "⚙️ Настройки\n"
        "\n"
        "🏙 Город: Москва\n"
        "🌅 Утренняя сводка: включена ✅\n"
        "🕗 Время сводки: 08:00\n"
        "🌐 Язык: как в Telegram (Русский)"
    )
    toggle_row = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[1]
    assert toggle_row[0].text == "🔕 Выключить сводку"
    await feed(callback_update(SettingsCb(action="toggle").pack()))
    edited = fake.of(EditMessageText)[-1]
    assert "🌅 Утренняя сводка: выключена ❌" in edited.text
    assert edited.reply_markup.inline_keyboard[1][0].text == "🔔 Включить сводку"


async def test_language_switch_sends_new_keyboard(feed, fake, session) -> None:
    await feed(callback_update(SettingsCb(action="lang").pack()))
    labels = [row[0].text for row in fake.of(EditMessageText)[-1].reply_markup.inline_keyboard]
    assert labels == ["🇷🇺 Русский", "🇬🇧 English", "📱 Как в Telegram", "↩️ Назад"]
    await feed(callback_update(SettingsCb(action="setlang", value="en").pack()))
    assert fake.of(EditMessageText)[-1].text.startswith("⚙️ Settings")
    last = fake.of(SendMessage)[-1]
    assert last.text == "✅ Language: English"
    assert isinstance(last.reply_markup, ReplyKeyboardMarkup)
    assert last.reply_markup.keyboard[0][0].text == "🌤 Weather"
    assert (await session.get(User, 1)).language == "en"
    await feed(callback_update(SettingsCb(action="setlang", value="auto").pack()))
    session.expire_all()  # the user row was changed by the bot's own session
    assert (await session.get(User, 1)).language is None
    assert fake.of(SendMessage)[-1].text == "✅ Язык: Русский"


async def test_city_single_match(feed, fake, meteo, session) -> None:
    meteo.cities = [SPB]
    await feed(callback_update(SettingsCb(action="city").pack()))
    assert fake.sent_texts()[-1] == "🏙 Напиши название города:"
    await feed(message_update("x" * 51))
    assert fake.sent_texts()[-1] == "Название города — текст до 50 символов. Попробуй ещё раз:"
    await feed(message_update("питер"))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Санкт-Петербург"
    user = await session.get(User, 1)
    assert (user.city, user.lat, user.timezone) == ("Санкт-Петербург", 59.94, "Europe/Moscow")


async def test_city_choice_between_several(feed, fake, meteo, session) -> None:
    meteo.cities = [SPB, SPB_US]
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Saint Petersburg"))
    choice = fake.of(SendMessage)[-1]
    assert choice.text == "Нашлось несколько городов — выбери свой:"
    assert [row[0].text for row in choice.reply_markup.inline_keyboard] == [
        "Санкт-Петербург, Россия",
        "Saint Petersburg, Florida, США",
    ]
    pick = choice.reply_markup.inline_keyboard[1][0].callback_data
    await feed(callback_update(pick))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Saint Petersburg"
    assert (await session.get(User, 1)).timezone == "America/New_York"
    await feed(callback_update(pick))  # stale choice
    assert fake.calls[-1].text == "Эта кнопка устарела — открой раздел заново из меню."


async def test_a_button_from_an_earlier_city_search_is_stale(feed, fake, meteo, session) -> None:
    meteo.cities = [SPB, SPB_US]
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Saint Petersburg"))
    first = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    meteo.cities = [SPB_US, SPB]  # the same cities in another order
    await feed(message_update("Петербург"))
    second = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    await feed(callback_update(first[1][0].callback_data))
    assert fake.calls[-1].text == "Эта кнопка устарела — открой раздел заново из меню."
    assert (await session.get(User, 1)).city == "Москва"
    await feed(callback_update(second[1][0].callback_data))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Санкт-Петербург"


async def test_city_not_found_and_service_down(feed, fake, meteo) -> None:
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Нигдебург"))
    assert fake.sent_texts()[-1] == (
        "Не нашёл город «Нигдебург». Проверь название и напиши ещё раз:"
    )
    meteo.fail = True
    await feed(message_update("Казань"))
    assert fake.sent_texts()[-1] == "⚠️ Сервис поиска городов недоступен. Попробуй позже."


async def test_morning_time(feed, fake, session) -> None:
    await feed(callback_update(SettingsCb(action="time").pack()))
    assert fake.sent_texts()[-1] == (
        "🕗 Во сколько присылать утреннюю сводку? Формат ЧЧ:ММ, например 07:30"
    )
    await feed(message_update("25:00"))
    assert fake.sent_texts()[-1] == "Не похоже на время. Нужен формат ЧЧ:ММ, например 07:30:"
    await feed(message_update("7:5"))
    assert fake.sent_texts()[-1] == "✅ Сводка будет приходить в 07:05"
    assert (await session.get(User, 1)).morning_time == "07:05"


async def test_weather_change_city_button_opens_the_dialog(feed, fake) -> None:
    await feed(message_update("🌤 Погода"))
    button = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[0][0]
    await feed(callback_update(button.callback_data))
    assert fake.sent_texts()[-1] == "🏙 Напиши название города:"
