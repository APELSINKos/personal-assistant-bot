from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Update
from sqlalchemy import select

from assistant.bot.keyboards import EntryCb
from assistant.bot.money_texts import month_name
from assistant.core.config import LIMITS
from assistant.core.i18n import translator
from assistant.core.models import MoneyCategory, MoneyEntry, User
from assistant.core.money_style import CATEGORY_EMOJI
from assistant.core.services import money
from assistant.core.timeutil import local_today
from tests.bot.fakes import callback_update, message_update

NBSP = "\u00a0"
RU = translator("ru")
STALE = "Эта кнопка устарела — открой раздел заново из меню."


def rub(amount: str) -> str:
    return amount.replace(" ", NBSP) + f"{NBSP}₽"


def press(action: str, entry_id: int, value: int = 0) -> Update:
    return callback_update(EntryCb(action=action, id=entry_id, value=value).pack())


def rows(message: SendMessage | EditMessageText) -> list[list[str]]:
    markup = message.reply_markup
    return [[button.text for button in row] for row in markup.inline_keyboard] if markup else []


async def entries(session) -> list[MoneyEntry]:
    return list(await session.scalars(select(MoneyEntry).order_by(MoneyEntry.id)))


async def preset(session, user: User, key: str) -> MoneyCategory:
    return next(item for item in await money.categories(session, user) if item.preset == key)


async def this_month(user: User) -> str:
    return month_name(local_today(user.timezone).replace(day=1), RU).capitalize()


async def test_a_phrase_becomes_an_expense_at_once(feed, fake, session, make_user) -> None:
    user = await make_user()
    await feed(message_update("кофе 250"))
    [entry] = await entries(session)
    assert (entry.amount, entry.note, entry.day) == (25000, "кофе", local_today(user.timezone))
    [reply] = fake.of(SendMessage)
    assert reply.text == f"✅ ☕ Кафе — {rub('250')} · кофе\n{await this_month(user)}: {rub('250')}"
    assert rows(reply) == [["🗂 Категория", "↩️ Отменить"]]


async def test_yesterday_an_income_and_a_bare_number(feed, fake, session, make_user) -> None:
    user = await make_user()
    await feed(message_update("вчера такси 300"))
    await feed(message_update("+5000 стипендия"))
    await feed(message_update("250"))
    taxi, stipend, other = await entries(session)
    assert taxi.day == local_today(user.timezone) - timedelta(days=1)
    first, second, third = (text.split("\n")[0] for text in fake.sent_texts())
    assert first == f"✅ 🚌 Транспорт — {rub('300')} · такси · вчера"
    assert second == f"✅ 🎓 Стипендия — +{rub('5 000')} · стипендия"
    assert third == f"✅ 📦 Другое — {rub('250')}"


async def test_a_reminder_phrase_stays_a_reminder_and_a_quantity_is_not_money(
    feed, fake, session, make_user
) -> None:
    await make_user()
    await feed(message_update("молоко 2 литра"))
    await feed(message_update("кофе 5$"))
    await feed(message_update("завтра в 9 купить молоко"))  # its card waits for «✅ Создать»
    assert await entries(session) == []
    quantity, dollars, reminder = fake.sent_texts()
    assert reminder.startswith("⏰ Завтра, 09:00 — купить молоко")
    assert quantity.startswith("🤔 Не понял")
    assert dollars == "Суммы записываются в ₽ — валюта меняется в ⚙️ Настройках."


async def test_another_category_is_remembered_for_the_note(feed, fake, session, make_user) -> None:
    user = await make_user()
    await feed(message_update("кофе 250"))
    [entry] = await entries(session)
    await feed(press("cat", entry.id))
    picker = fake.of(EditMessageText)[-1]
    assert picker.text == "🗂 Куда записать «кофе»?"
    buttons = rows(picker)
    assert buttons[0] == ["🛒 Продукты", "✓ ☕ Кафе"]
    assert buttons[-2:] == [["🔁 Это доход", "➕ Новая"], ["↩️ Назад"]]
    groceries = await preset(session, user, "groceries")
    await feed(press("set", entry.id, groceries.id))
    assert fake.of(EditMessageText)[-1].text.startswith(f"✅ 🛒 Продукты — {rub('250')} · кофе")
    await feed(message_update("Кофе 100"))  # the same note, another case
    assert fake.sent_texts()[-1].startswith(f"✅ 🛒 Продукты — {rub('100')} · Кофе")
    await feed(press("kind", entry.id, 1))
    incomes = rows(fake.of(EditMessageText)[-1])
    assert incomes[0] == ["💼 Зарплата", "🎓 Стипендия"]
    assert incomes[-2] == ["🔁 Это расход", "➕ Новая"]
    await feed(press("back", entry.id))
    assert rows(fake.of(EditMessageText)[-1]) == [["🗂 Категория", "↩️ Отменить"]]


async def test_undo_and_a_button_of_an_entry_that_is_gone(feed, fake, session, make_user) -> None:
    await make_user()
    await feed(message_update("кофе 250"))
    [entry] = await entries(session)
    await feed(press("undo", entry.id))
    undone = fake.of(EditMessageText)[-1]
    assert undone.text == f"↩️ Отменено: ☕ Кафе — {rub('250')} · кофе"
    assert undone.reply_markup is None
    assert await entries(session) == []
    for action in ("undo", "cat", "set"):
        await feed(press(action, entry.id, 1))
        assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."


def too_old() -> TelegramBadRequest:
    return TelegramBadRequest(
        method=AnswerCallbackQuery(callback_query_id="1"),
        message="Bad Request: query is too old and response timeout expired",
    )


async def test_an_expired_button_still_shows_what_it_did(feed, fake, session, make_user) -> None:
    # Taps that waited out a restart arrive too old to answer: the work is done all the same.
    user = await make_user()
    await feed(message_update("кофе 250"))
    await feed(message_update("такси 300"))
    coffee, taxi = await entries(session)
    groceries = await preset(session, user, "groceries")
    fake.errors.append(too_old())
    await feed(press("set", coffee.id, groceries.id))
    assert fake.of(EditMessageText)[-1].text.startswith(f"✅ 🛒 Продукты — {rub('250')} · кофе")
    fake.errors.append(too_old())
    await feed(press("undo", taxi.id))
    assert fake.of(EditMessageText)[-1].text == f"↩️ Отменено: 🚌 Транспорт — {rub('300')} · такси"
    await feed(press("new", coffee.id, 0))
    await feed(message_update("Кофейни"))
    fake.errors.append(too_old())
    await feed(press("emoji", coffee.id, CATEGORY_EMOJI.index("☕")))
    assert fake.of(SendMessage)[-1].text == "✅ Новая категория: ☕ Кофейни"
    assert fake.of(EditMessageText)[-1].text.startswith(f"✅ ☕ Кофейни — {rub('250')} · кофе")
    assert not any("Что-то пошло не так" in text for text in fake.sent_texts())


async def test_a_command_with_a_number_is_not_money(feed, fake, session, make_user) -> None:
    await make_user()
    await feed(message_update("/note 7"))
    await feed(message_update("/foo 250"))
    assert await entries(session) == []
    assert [text.split("\n")[0] for text in fake.sent_texts()] == [
        "🤔 Не понял. Выбери раздел в меню ниже 👇"
    ] * 2


async def test_another_users_entry_is_gone_for_this_one(feed, fake, session, make_user) -> None:
    stranger = await make_user(2)
    cafe = await preset(session, stranger, "cafe")
    theirs = await money.add_entry(session, stranger, amount=100, category_id=cafe.id)
    await session.commit()
    await make_user(1)
    await feed(press("undo", theirs.id))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert len(await entries(session)) == 1


async def test_a_new_category_with_a_name_and_an_emoji(feed, fake, session, make_user) -> None:
    user = await make_user()
    await feed(message_update("бургер 450"))
    [entry] = await entries(session)
    await feed(press("new", entry.id, 0))
    assert fake.sent_texts()[-1] == "✍️ Название новой категории (до 30 символов):"
    await feed(message_update("кафе"))  # a preset's name
    assert fake.sent_texts()[-1] == "Такая категория уже есть — придумай другое название:"
    await feed(message_update("Фастфуд"))
    grid = fake.of(SendMessage)[-1]
    assert grid.text == "🎨 Эмодзи для «Фастфуд»:"
    assert [len(row) for row in rows(grid)] == [8, 8, 8, 8, 8]
    await feed(press("emoji", entry.id, CATEGORY_EMOJI.index("🍔")))
    assert fake.of(SendMessage)[-1].text == "✅ Новая категория: 🍔 Фастфуд"
    assert fake.of(EditMessageText)[-1].text.startswith(f"✅ 🍔 Фастфуд — {rub('450')} · бургер")
    await feed(message_update("бургер 300"))
    assert fake.sent_texts()[-1].startswith("✅ 🍔 Фастфуд")
    assert user.id == entry.user_id


async def test_an_emoji_without_the_dialog_is_a_stale_button(
    feed, fake, session, make_user
) -> None:
    await make_user()
    await feed(message_update("кофе 250"))
    [entry] = await entries(session)
    await feed(press("emoji", entry.id, 0))
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    await feed(press("kind", entry.id, 7))
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE


async def test_a_budget_warning_follows_the_entry(feed, fake, session, make_user) -> None:
    user = await make_user()
    await money.set_budget(session, user, 100000)
    await session.commit()
    await feed(message_update("кофе 790"))
    await feed(message_update("кофе 20"))
    month = month_name(local_today(user.timezone).replace(day=1), RU)
    assert fake.sent_texts()[-1] == (
        f"⚠️ Потрачено 81 % бюджета на {month}: {rub('810')} из {rub('1 000')}"
    )
    await feed(message_update("кофе 1"))
    assert not fake.sent_texts()[-1].startswith("⚠️")


async def test_the_month_limit(feed, fake, session, make_user, monkeypatch) -> None:
    await make_user()
    monkeypatch.setattr(money, "LIMITS", replace(LIMITS, money_entries_month=1))
    await feed(message_update("кофе 1"))
    await feed(message_update("кофе 2"))
    assert fake.sent_texts()[-1].startswith("В этом месяце уже 1")
    assert len(await entries(session)) == 1
