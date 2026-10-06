from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
)
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy import select

from assistant.bot.keyboards import CityCb, SettingsCb
from assistant.core.clients.openmeteo import City
from assistant.core.models import Reminder, Repeat, User
from assistant.core.services import cities, reminders
from assistant.core.services.recurrence import Rule
from tests.bot.fakes import callback_update, message_update

SPB = City(
    name="Санкт-Петербург",
    admin="Санкт-Петербург",
    country="Россия",
    lat=59.94,
    lon=30.31,
    timezone="Europe/Moscow",
    geo_id=498817,
)
SPB_US = City(
    name="Saint Petersburg",
    admin="Florida",
    country="США",
    lat=27.77,
    lon=-82.68,
    timezone="America/New_York",
    geo_id=4171563,
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
SOCHI = replace(TULA, name="Сочи", admin="Краснодарский край", lat=43.6, lon=39.73, geo_id=491422)
KAZAN = replace(TULA, name="Казань", admin="Татарстан", lat=55.79, lon=49.12, geo_id=551487)
OMSK = replace(
    TULA,
    name="Омск",
    admin="Омская область",
    lat=54.99,
    lon=73.37,
    timezone="Asia/Omsk",
    geo_id=1496153,
)
KAMCHATKA = replace(
    TULA,
    name="Петропавловск-Камчатский",
    admin="Камчатский край",
    lat=53.04,
    lon=158.65,
    timezone="Asia/Kamchatka",
    geo_id=2122104,
)
MOSCOW = replace(TULA, name="Москва", admin="Москва", lat=55.75, lon=37.62, geo_id=524901)
MOSCOW_US = City(
    name="Москва",
    admin="Айдахо",
    country="США",
    lat=46.73,
    lon=-117.0,
    timezone="America/Los_Angeles",
    geo_id=5601538,
)
STALE = "Эта кнопка устарела — открой раздел заново из меню."
DUPLICATE = "Этот город уже в списке. Напиши другой:"
FULL = "Можно добавить не больше 4 городов."
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def buttons(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.inline_keyboard]


async def keep(session, make_user, *places: City) -> User:
    """The user with these extra cities, added as the app adds them."""
    user = await make_user()
    for place in places:
        await cities.add(session, user, place)
    await session.commit()
    return user


async def names(session) -> list[str]:
    return [city.name for city in await cities.list_for(session, 1)]


async def test_settings_view_and_toggle(feed, fake) -> None:
    await feed(message_update("/settings"))
    assert fake.sent_texts()[-1] == (
        "⚙️ Настройки\n"
        "\n"
        "🏙 Город: Москва\n"
        "🌅 Утренняя сводка: включена ✅\n"
        "🕗 Время сводки: 08:00\n"
        "🌐 Язык: как в Telegram (Русский)\n"
        "💱 Валюта: ₽ (RUB)"
    )
    city_row = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[0]
    assert [button.text for button in city_row] == ["🏙 Города", "🕗 Время сводки"]
    assert city_row[0].callback_data == CityCb(action="list", back="s").pack()
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


async def test_the_cities_without_extra_ones(feed, fake) -> None:
    await feed(callback_update(CityCb(action="list").pack()))
    view = fake.of(EditMessageText)[-1]
    assert view.text == (
        "🏙 Города\n"
        "\n"
        "🏠 Москва — домашний город: по его времени приходят напоминания и сводка\n"
        "\n"
        "Других городов пока нет — добавь до 4, и их погода будет под «🌤 Погодой» одной "
        "кнопкой."
    )
    assert buttons(view) == [["✏️ Сменить домашний"], ["➕ Добавить город"], ["↩️ Назад"]]
    change, add, back = (row[0].callback_data for row in view.reply_markup.inline_keyboard)
    assert add == CityCb(action="add", back="s").pack()
    await feed(callback_update(back))
    assert fake.of(EditMessageText)[-1].text.startswith("⚙️ Настройки\n")
    await feed(callback_update(change))  # the home city is changed as before
    assert fake.sent_texts()[-1] == "🏙 Напиши название города:"


async def test_the_cities_in_english(feed, fake) -> None:
    await feed(callback_update(CityCb(action="list").pack(), lang="en"))
    view = fake.of(EditMessageText)[-1]
    assert view.text == (
        "🏙 Cities\n"
        "\n"
        "🏠 Москва — home city: reminders and the morning digest follow its time\n"
        "\n"
        "No other cities yet — add up to 4, and their weather will be one tap away under "
        "“🌤 Weather”."
    )
    assert buttons(view) == [["✏️ Change home city"], ["➕ Add a city"], ["↩️ Back"]]


async def test_extra_cities_with_a_delete_button_each(feed, fake, session, make_user) -> None:
    user = await keep(session, make_user, TULA, SOCHI, KAMCHATKA)
    await feed(callback_update(CityCb(action="list").pack()))
    view = fake.of(EditMessageText)[-1]
    assert view.text.split("\n")[2:] == [
        "🏠 Москва — домашний город: по его времени приходят напоминания и сводка",
        "",
        "• Тула",
        "• Сочи",
        "• Петропавловск-Камчатский",
    ]
    assert buttons(view) == [
        ["✏️ Сменить домашний"],
        ["🗑 Тула", "🗑 Сочи"],
        ["🗑 Петропавловск-Камча…"],
        ["➕ Добавить город"],
        ["↩️ Назад"],
    ]
    await cities.add(session, user, OMSK)
    await session.commit()
    await feed(callback_update(CityCb(action="list").pack()))
    view = fake.of(EditMessageText)[-1]
    assert buttons(view)[2:] == [["🗑 Петропавловск-Камча…", "🗑 Омск"], ["↩️ Назад"]]  # no room
    packed = [button.callback_data for row in view.reply_markup.inline_keyboard for button in row]
    assert all(len(data.encode()) <= 64 for data in packed)


async def test_a_city_is_deleted_at_once(feed, fake, session, make_user) -> None:
    await keep(session, make_user, TULA, SOCHI)
    await feed(callback_update(CityCb(action="list").pack()))
    delete = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[1][0].callback_data
    assert CityCb.unpack(delete).action == "del"
    await feed(callback_update(delete))
    assert fake.of(AnswerCallbackQuery)[-1].text == "🗑 Удалено"
    view = fake.of(EditMessageText)[-1]
    assert view.text.endswith("\n\n• Сочи")
    assert buttons(view)[1] == ["🗑 Сочи"]
    await feed(callback_update(delete))  # from the sub-view shown before
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого города уже нет в списке"
    assert fake.of(EditMessageText)[-1].text == view.text
    assert await names(session) == ["Сочи"]


async def test_another_users_city_is_not_deleted(feed, fake, session, make_user) -> None:
    other = await make_user(id=2)
    theirs = await cities.add(session, other, TULA)
    await session.commit()
    await feed(callback_update(CityCb(action="del", id=theirs.id).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого города уже нет в списке"
    assert [city.name for city in await cities.list_for(session, 2)] == ["Тула"]


async def test_the_buttons_keep_where_the_sub_view_was_opened(
    feed, fake, session, make_user
) -> None:
    await keep(session, make_user, TULA, SOCHI)
    [tula, _] = await cities.list_for(session, 1)
    await feed(callback_update(CityCb(action="del", id=tula.id, back="w").pack()))
    view = fake.of(EditMessageText)[-1]
    packed = [
        CityCb.unpack(button.callback_data)
        for row in view.reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("c:")
    ]
    assert [(data.action, data.back) for data in packed] == [("del", "w"), ("add", "w")]


async def test_a_forged_way_back_is_a_stale_button(feed, fake, session, make_user) -> None:
    user = await make_user()
    for _ in range(10):  # a two-digit id: a forged way back carried into its button overflows
        await cities.delete(session, user.id, (await cities.add(session, user, TULA)).id)
    await cities.add(session, user, TULA)
    await session.commit()
    longest = "c:del:0:" + "x" * 55 + ":"
    assert len(longest.encode()) == 64  # Telegram takes it
    for data in ("c:list:0:x:", longest):
        await feed(callback_update(data))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    assert fake.sent_texts() == []  # no sub-view, no «something went wrong»
    assert await names(session) == ["Тула"]


async def test_adding_the_one_city_found(feed, fake, meteo, session, make_user) -> None:
    await make_user()
    await feed(callback_update(CityCb(action="add").pack()))
    ask = fake.of(SendMessage)[-1]
    assert ask.text == "🏙 Какой город добавить? Напиши название:"
    assert [[button.text for button in row] for row in ask.reply_markup.keyboard] == [["❌ Отмена"]]
    await feed(message_update(None, sticker=True))
    assert fake.sent_texts()[-1] == "Нужен текст. Напиши название города, который добавить."
    await feed(message_update("x" * 51))
    assert fake.sent_texts()[-1] == "Название города — текст до 50 символов. Попробуй ещё раз:"
    meteo.cities = [OMSK]
    await feed(message_update(" Омск "))
    assert meteo.searches[-1] == ("Омск", "ru")
    done = fake.of(SendMessage)[-1]
    assert done.text == "✅ Город добавлен: Омск. Его погода — кнопкой «Омск» под «🌤 Погодой»."
    assert done.reply_markup.keyboard[0][0].text == "🌤 Погода"  # the main menu
    [omsk] = await cities.list_for(session, 1)
    assert (omsk.name, omsk.admin, omsk.timezone, omsk.geo_id) == (
        "Омск",
        "Омская область",
        "Asia/Omsk",
        1496153,
    )
    await feed(message_update("Тула"))  # the dialog is over
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_a_choice_when_adding_leaves_the_home_city(
    feed, fake, meteo, session, make_user
) -> None:
    await make_user()
    meteo.cities = [SPB, SPB_US]
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Saint Petersburg"))
    choice = fake.of(SendMessage)[-1]
    assert choice.text == "Нашлось несколько городов — выбери нужный:"
    assert buttons(choice) == [["Санкт-Петербург, Россия"], ["Saint Petersburg, Florida, США"]]
    pick = CityCb.unpack(choice.reply_markup.inline_keyboard[1][0].callback_data)
    assert (pick.action, pick.id, len(pick.token)) == ("pick", 1, 8)
    await feed(callback_update(pick.pack()))
    assert fake.of(EditMessageReplyMarkup)[-1].reply_markup is None  # the choice is over
    done = fake.of(SendMessage)[-1]
    assert done.text == (
        "✅ Город добавлен: Saint Petersburg. Его погода — кнопкой «Saint Petersburg» "
        "под «🌤 Погодой»."
    )
    assert isinstance(done.reply_markup, ReplyKeyboardMarkup)
    session.expire_all()
    home = await session.get_one(User, 1)
    assert (home.city, home.lat, home.lon, home.timezone) == (
        "Москва",
        55.75,
        37.62,
        "Europe/Moscow",
    )
    assert [(city.name, city.timezone) for city in await cities.list_for(session, 1)] == [
        ("Saint Petersburg", "America/New_York")
    ]
    await feed(callback_update(pick.pack()))  # the same choice again
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE


async def test_the_choices_of_the_two_dialogs_do_not_mix(feed, fake, meteo, session) -> None:
    meteo.cities = [SPB, SPB_US]
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Saint Petersburg"))
    added = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[1][0].callback_data
    token = CityCb.unpack(added).token
    # A choice of the home city does not read the search of a city being added…
    await feed(callback_update(SettingsCb(action="pick", value=f"{token}-1").pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Saint Petersburg"))
    home = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[1][0].callback_data
    search = SettingsCb.unpack(home).value.partition("-")[0]
    # …nor a choice of a city to add the home city's search; the earlier choice is stale now.
    for stale in (CityCb(action="pick", id=1, token=search).pack(), added):
        await feed(callback_update(stale))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    assert await names(session) == []
    session.expire_all()
    assert (await session.get_one(User, 1)).city == "Москва"
    await feed(callback_update(home))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Saint Petersburg"


async def test_a_city_on_the_list_or_the_home_city_is_refused(
    feed, fake, meteo, session, make_user
) -> None:
    await keep(session, make_user, TULA)
    await feed(callback_update(CityCb(action="add").pack()))
    for place in (TULA, MOSCOW):
        meteo.cities = [place]
        await feed(message_update(place.name))
        assert fake.sent_texts()[-1] == DUPLICATE
    meteo.cities = [SOCHI]
    await feed(message_update("Сочи"))  # the dialog waited for another name
    assert fake.sent_texts()[-1].startswith("✅ Город добавлен: Сочи.")
    meteo.cities = [MOSCOW, MOSCOW_US]
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Москва"))
    choice = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    assert [row[0].text for row in choice] == ["Москва, Россия", "Москва, Айдахо, США"]
    await feed(callback_update(choice[0][0].callback_data))  # the home city
    assert fake.sent_texts()[-1] == DUPLICATE
    assert fake.of(EditMessageReplyMarkup) == []  # the choice stays: the namesake is there
    await feed(callback_update(choice[1][0].callback_data))
    assert fake.sent_texts()[-1].startswith("✅ Город добавлен: Москва.")
    assert await names(session) == ["Тула", "Сочи", "Москва"]


async def test_a_list_filled_up_during_the_dialog_ends_it(
    feed, fake, meteo, session, make_user
) -> None:
    user = await keep(session, make_user, TULA, SOCHI, KAZAN)
    await feed(callback_update(CityCb(action="add").pack()))
    fourth = await cities.add(session, user, OMSK)  # meanwhile in the app
    await session.commit()
    meteo.cities = [MOSCOW, MOSCOW_US]  # namesakes, yet no choice: the name is not even searched
    await feed(message_update("Москва"))
    done = fake.of(SendMessage)[-1]
    assert (done.text, isinstance(done.reply_markup, ReplyKeyboardMarkup)) == (FULL, True)
    assert meteo.searches == []
    await feed(message_update("Сочи"))  # the dialog is over
    assert fake.sent_texts()[-1].startswith("🤔")
    # The same when it fills up while the choice between namesakes is shown.
    await cities.delete(session, user.id, fourth.id)
    await session.commit()
    meteo.cities = [MOSCOW_US, SPB_US]
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Москва"))
    choice = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    await cities.add(session, user, OMSK)
    await session.commit()
    await feed(callback_update(choice[0][0].callback_data))
    assert fake.of(EditMessageReplyMarkup)[-1].reply_markup is None
    done = fake.of(SendMessage)[-1]
    assert (done.text, isinstance(done.reply_markup, ReplyKeyboardMarkup)) == (FULL, True)
    await feed(callback_update(choice[1][0].callback_data))
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    assert await names(session) == ["Тула", "Сочи", "Казань", "Омск"]


async def test_add_on_an_older_sub_view_with_four_cities(feed, fake, session, make_user) -> None:
    await keep(session, make_user, TULA, SOCHI, KAZAN, OMSK)
    await feed(callback_update(CityCb(action="add").pack()))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert (answer.text, answer.show_alert) == (FULL, True)
    view = fake.of(EditMessageText)[-1]
    assert view.text.startswith("🏙 Города\n") and ["➕ Добавить город"] not in buttons(view)
    assert fake.of(SendMessage) == []  # no dialog
    await feed(message_update("Тула"))
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_adding_when_nothing_is_found_or_the_service_is_down(feed, fake, meteo) -> None:
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Нигдебург"))
    assert fake.sent_texts()[-1] == (
        "Не нашёл город «Нигдебург». Проверь название и напиши ещё раз:"
    )
    meteo.cities = [replace(TULA, timezone="Mars/Base")]  # a place that cannot be kept
    await feed(message_update("Тула"))
    assert fake.sent_texts()[-1] == "Не нашёл город «Тула». Проверь название и напиши ещё раз:"
    meteo.fail = True
    await feed(message_update("Казань"))
    done = fake.of(SendMessage)[-1]
    assert done.text == "⚠️ Сервис поиска городов недоступен. Попробуй позже."
    assert isinstance(done.reply_markup, ReplyKeyboardMarkup)
    meteo.fail = False
    await feed(message_update("Казань"))  # the dialog is over
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_a_chosen_place_that_cannot_be_kept_is_not_found(feed, fake, meteo, session) -> None:
    meteo.cities = [replace(TULA, timezone="Mars/Base"), SOCHI]  # the first one cannot be kept
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Тула"))
    choice = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    await feed(callback_update(choice[0][0].callback_data))
    assert fake.of(AnswerCallbackQuery)[-1].text is None  # not a stale button
    assert fake.sent_texts()[-1] == "Не нашёл город «Тула». Проверь название и напиши ещё раз:"
    assert fake.of(EditMessageReplyMarkup) == []  # the choice stays
    meteo.cities = [KAZAN]
    await feed(message_update("Казань"))  # the dialog waited for a name
    assert fake.sent_texts()[-1].startswith("✅ Город добавлен: Казань.")
    assert await names(session) == ["Казань"]


async def test_a_new_home_city_leaves_the_extra_ones(feed, fake, meteo, session, make_user) -> None:
    await keep(session, make_user, TULA, SOCHI, KAZAN)
    # The search may put a place a little off the point kept for it (here by 0.014°): then
    # only the GeoNames id tells that the new home city is the one on the list.
    meteo.cities = [replace(TULA, lat=54.2044, lon=37.6111)]
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Тула"))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Тула"
    assert await names(session) == ["Сочи", "Казань"]
    meteo.cities = [KAZAN, replace(SOCHI, lat=43.585, lon=39.7203)]
    await feed(callback_update(SettingsCb(action="city").pack()))
    await feed(message_update("Сочи"))
    choice = fake.of(SendMessage)[-1].reply_markup.inline_keyboard
    await feed(callback_update(choice[1][0].callback_data))
    assert fake.sent_texts()[-1] == "✅ Город сохранён: Сочи"
    assert await names(session) == ["Казань"]


async def test_extra_cities_move_neither_the_home_zone_nor_the_reminders(
    feed, fake, meteo, session, make_user
) -> None:
    user = await make_user()
    daily = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 10, 5))
    await reminders.create_repeating(session, user, "таблетки", daily, NOW)
    await reminders.create(session, user, "врач", datetime(2026, 10, 6, 10), NOW)
    await session.commit()
    moments = select(Reminder.due_at, Reminder.occurrence_at).order_by(Reminder.id)
    before = (await session.execute(moments)).all()
    meteo.cities = [OMSK]  # three hours ahead of the home city
    await feed(callback_update(CityCb(action="add").pack()))
    await feed(message_update("Омск"))
    [omsk] = await cities.list_for(session, 1)
    await feed(callback_update(CityCb(action="del", id=omsk.id).pack()))
    assert await names(session) == []
    session.expire_all()
    assert (await session.get_one(User, 1)).timezone == "Europe/Moscow"
    assert (await session.execute(moments)).all() == before


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


async def test_an_expired_button_still_saves_and_shows_the_setting(feed, fake) -> None:
    # A tap that waited out a restart is too old to answer: the change is saved and shown anyway.
    for data, shown in (
        (SettingsCb(action="setcurrency", value="KZT"), "💱 Валюта: ₸ (KZT)"),
        (SettingsCb(action="toggle"), "🌅 Утренняя сводка: выключена"),
    ):
        fake.errors.append(
            TelegramBadRequest(
                method=AnswerCallbackQuery(callback_query_id="1"),
                message="Bad Request: query is too old and response timeout expired",
            )
        )
        await feed(callback_update(data.pack()))
        assert shown in fake.of(EditMessageText)[-1].text
    assert not any("Что-то пошло не так" in text for text in fake.sent_texts())


async def test_the_currency_of_the_accounts(feed, fake, session) -> None:
    await feed(callback_update(SettingsCb(action="currency").pack()))
    picker = fake.of(EditMessageText)[-1]
    assert picker.text.startswith("💱 В какой валюте вести учёт?")
    rows = [[button.text for button in row] for row in picker.reply_markup.inline_keyboard]
    assert rows[0] == ["₽ RUB", "$ USD", "€ EUR", "₸ KZT"]
    assert len(rows) == 5 and rows[-1] == ["↩️ Назад"]
    await feed(callback_update(SettingsCb(action="setcurrency", value="KZT").pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Валюта: ₸"
    assert fake.of(EditMessageText)[-1].text.endswith("💱 Валюта: ₸ (KZT)")
    session.expire_all()
    assert (await session.get(User, 1)).currency == "KZT"
    await feed(callback_update(SettingsCb(action="setcurrency", value="XXX").pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text.startswith("Эта кнопка устарела")
