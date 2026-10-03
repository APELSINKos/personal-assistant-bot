from __future__ import annotations

from datetime import date, timedelta

from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendMessage, SendPhoto
from aiogram.types import Update
from aiogram.types import User as TgUser

from assistant.bot.keyboards import MoneyCb
from assistant.core.models import MoneyCategory, User
from assistant.core.services import money, money_month
from assistant.core.services.money_cards import month_title
from assistant.core.services.money_phrases import format_amount
from assistant.core.timeutil import local_today
from tests.bot.fakes import callback_update, message_update

NBSP = "\u00a0"
STALE = "Эта кнопка устарела — открой раздел заново из меню."
BOT = TgUser(id=99, is_bot=True, first_name="Помощник", username="assistant_bot")


def press(action: str, value: str = "") -> Update:
    return callback_update(MoneyCb(action=action, value=value).pack())


def rub(amount: str) -> str:
    return amount.replace(" ", NBSP) + f"{NBSP}₽"


def money_text(hundredths: int) -> str:
    return format_amount(hundredths, "RUB", "ru")


def buttons(message: SendMessage | SendPhoto) -> list[list[str]]:
    markup = message.reply_markup
    return [[button.text for button in row] for row in markup.inline_keyboard] if markup else []


async def preset(session, user: User, key: str) -> MoneyCategory:
    return next(item for item in await money.categories(session, user) if item.preset == key)


async def spend(session, user: User, key: str, amount: int, day: date | None = None) -> None:
    category = await preset(session, user, key)
    await money.add_entry(session, user, amount=amount, category_id=category.id, day=day)
    await session.commit()


async def test_the_menu_opens_money_and_so_does_the_old_rates_label(feed, fake) -> None:
    await feed(message_update("💰 Финансы"))
    await feed(message_update("💱 Курс валют"))  # a keyboard shown before 2.5 keeps this label
    first, second = fake.of(SendMessage)
    assert first.text == second.text and first.text.startswith("💰 ")
    assert buttons(first) == [["📊 Отчёт", "📜 Записи"], ["🎯 Бюджет", "💱 Курсы"]]


async def test_start_names_the_money_section(feed, fake) -> None:
    await feed(message_update("/start"))
    await feed(message_update("/start", user_id=2, lang="en"))
    ru, en = (text.split("\n") for text in fake.sent_texts())
    assert "💰 Финансы — траты, бюджет и курсы валют" in ru
    assert "💰 Money — expenses, budget and exchange rates" in en
    assert not any("💱" in line for line in [*ru, *en])  # the rates live in the money section


async def test_the_month_so_far(feed, fake, session, make_user) -> None:
    user = await make_user()
    today = local_today(user.timezone)
    await money.set_budget(session, user, 3000000)
    await spend(session, user, "groceries", 520000)
    await spend(session, user, "cafe", 310000)
    await spend(session, user, "salary", 2500000)
    await feed(message_update("💰 Финансы"))
    days_left = ((today.replace(day=28) + timedelta(days=4)).replace(day=1) - today).days
    per_day = (3000000 - 830000) // days_left
    assert fake.sent_texts()[-1].split("\n") == [
        f"💰 {month_title(today.replace(day=1), 'ru')}",
        f"Потрачено: {rub('8 300')} из {rub('30 000')} (28 %)",
        f"Доходы: {rub('25 000')} · баланс +{rub('16 700')}",
        f"Осталось {rub('21 700')} — по {money_text(per_day)} в день",
        "",
        f"▰▰▰▱▱ 🛒 Продукты — {rub('5 200')} (63 %)",
        f"▰▰▱▱▱ ☕ Кафе — {rub('3 100')} (37 %)",
        "",
        "Чтобы записать трату, просто напиши: кофе 250. Доход — со знаком +: +5000 стипендия",
    ]


async def test_a_month_with_incomes_only_has_no_expenses_yet(
    feed, fake, session, make_user
) -> None:
    user = await make_user()
    await spend(session, user, "salary", 500000)
    await feed(message_update("💰 Финансы"))
    lines = fake.sent_texts()[-1].split("\n")
    assert lines[1:5] == [
        f"Потрачено: 0{NBSP}₽",
        f"Доходы: {rub('5 000')} · баланс +{rub('5 000')}",
        "",
        "Трат в этом месяце пока нет.",
    ]


async def test_an_empty_month_in_english(feed, fake, make_user) -> None:
    await make_user(language="en")
    await feed(message_update("💰 Money", lang="en"))
    lines = fake.sent_texts()[-1].split("\n")
    assert lines[1:] == [
        f"Spent: 0{NBSP}₽",
        "",
        "No expenses this month yet.",
        "",
        "To note an expense, just write: coffee 250. Income goes with a plus: +5000 salary",
    ]


async def test_the_month_report_and_the_one_before(feed, fake, session, make_user) -> None:
    user = await make_user()
    today = local_today(user.timezone)
    first = today.replace(day=1)
    before = (first - timedelta(days=1)).replace(day=1)
    fake.results[GetMe] = BOT
    await spend(session, user, "cafe", 25000)
    await feed(press("report"))
    [photo] = fake.of(SendPhoto)
    assert photo.caption == f"💰 {month_title(first, 'ru')}: потрачено {rub('250')}"
    assert buttons(photo) == []  # nothing earlier
    await spend(session, user, "cafe", 99900, first - timedelta(days=1))
    await feed(press("report"))
    assert buttons(fake.of(SendPhoto)[-1]) == [[f"◀️ {month_title(before, 'ru')}"]]
    await feed(press("report", before.strftime("%Y-%m")))
    last = fake.of(SendPhoto)[-1]
    assert last.caption == f"💰 {month_title(before, 'ru')}: потрачено {rub('999')}"


async def test_a_forged_or_future_month_is_a_stale_button(feed, fake, make_user) -> None:
    user = await make_user()
    later = (local_today(user.timezone).replace(day=28) + timedelta(days=4)).replace(day=1)
    for value in ("2026-99", "nope", later.strftime("%Y-%m")):
        await feed(press("report", value))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE
    assert fake.of(SendPhoto) == []


async def test_at_most_six_pictures_a_minute(feed, fake, monotonic) -> None:
    fake.results[GetMe] = BOT
    for _ in range(6):
        await feed(press("report"))
    await feed(press("chart"))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and answer.text.startswith("⏳ Слишком много карточек подряд")
    assert len(fake.of(SendPhoto)) == 6
    monotonic[0] += 61
    await feed(press("chart"))
    assert len(fake.of(SendPhoto)) == 7


async def test_the_rates_with_the_converter_and_30_days(feed, fake, cbr) -> None:
    fake.results[GetMe] = BOT
    await feed(press("rates"))
    [rates] = fake.of(SendMessage)
    assert rates.text.startswith("💱 Курс ЦБ РФ на 28 сентября")
    assert buttons(rates) == [
        ["USD → ₽", "EUR → ₽"], ["₽ → USD", "₽ → EUR"], ["📈 30 дней"],
    ]  # fmt: skip
    await feed(press("chart"))
    [photo] = fake.of(SendPhoto)
    assert photo.caption == "📈 Курсы ЦБ за 30 дней"
    cbr.history_fail = True
    await feed(press("chart"))
    assert fake.sent_texts()[-1] == "⚠️ Не удалось получить курсы. Попробуй чуть позже."


async def test_a_forged_huge_id_is_a_stale_button(feed, fake) -> None:
    for data in ("h:open:9223372036854775808:", "n:del:-1:0", "m:report:99999999999999999999::"):
        await feed(callback_update(data))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE


def edited(fake) -> EditMessageText:
    return fake.of(EditMessageText)[-1]


async def test_the_entries_of_the_month_ten_a_page(feed, fake, session, make_user) -> None:
    user = await make_user()
    for amount in range(1, 13):
        await spend(session, user, "cafe", amount * 100)
    await feed(press("entries"))
    page = edited(fake)
    lines = page.text.split("\n")
    assert lines[0].endswith("· 12 записей")
    assert lines[2].startswith("1. ") and lines[2].endswith(f"☕ Кафе — {rub('12')}")
    assert lines[-1] == "Стр. 1 из 2"
    assert buttons(page) == [
        ["🗑 1", "🗑 2", "🗑 3", "🗑 4", "🗑 5"],
        ["🗑 6", "🗑 7", "🗑 8", "🗑 9", "🗑 10"],
        ["▶️"],
        ["↩️ Назад"],
    ]
    await feed(callback_update(MoneyCb(action="entries", page=1).pack()))
    assert buttons(edited(fake))[0] == ["🗑 11", "🗑 12"]


async def test_an_entry_is_deleted_after_a_confirmation(feed, fake, session, make_user) -> None:
    user = await make_user()
    await spend(session, user, "cafe", 25000)
    [(entry, _)] = await money_month.entries(
        session, user, local_today(user.timezone).replace(day=1)
    )
    await feed(callback_update(MoneyCb(action="delask", id=entry.id).pack()))
    assert edited(fake).text == f"🗑 Удалить «☕ Кафе — {rub('250')}»?"
    assert buttons(edited(fake)) == [["🗑 Да, удалить", "↩️ Назад"]]
    await feed(callback_update(MoneyCb(action="del", id=entry.id).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "🗑 Удалено"
    assert edited(fake).text == "📜 Записей в этом месяце пока нет."
    await feed(callback_update(MoneyCb(action="del", id=entry.id).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(callback_update(MoneyCb(action="delask", id=entry.id).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."


async def test_the_total_budget_is_set_and_removed(feed, fake, session, make_user) -> None:
    user_id = (await make_user()).id
    await feed(press("budget"))
    assert "Общий бюджет не задан." in edited(fake).text
    await feed(press("budgetset"))
    assert fake.sent_texts()[-1].startswith("🎯 Сколько можно потратить за месяц?")
    await feed(message_update("тридцать"))
    assert fake.sent_texts()[-1].startswith("Нужна сумма числом")
    await feed(message_update("30к"))
    saved, view = fake.sent_texts()[-2:]
    assert saved == "✅ Бюджет сохранён."
    assert f"Общий: {rub('30 000')} — потрачено {rub('0')}, осталось {rub('30 000')}" in view
    session.expire_all()  # the bot changed the row in its own session
    assert (await session.get(User, user_id)).money_budget == 3000000
    await feed(press("budgetset"))
    await feed(message_update("0"))
    assert fake.sent_texts()[-2] == "✅ Бюджет убран."


async def test_a_category_budget_and_its_overspending(feed, fake, session, make_user) -> None:
    user = await make_user()
    await spend(session, user, "cafe", 600000)
    cafe = await preset(session, user, "cafe")
    await feed(press("budgetcats"))
    assert edited(fake).text == "🗂 Какой категории задать бюджет?"
    assert buttons(edited(fake))[0] == ["🛒 Продукты", "☕ Кафе"]
    await feed(callback_update(MoneyCb(action="budgetset", id=cafe.id).pack()))
    assert fake.sent_texts()[-1].startswith("🎯 Бюджет «☕ Кафе» на месяц?")
    await feed(message_update("5 000 ₽"))
    view = fake.sent_texts()[-1]
    assert f"☕ Кафе: {rub('5 000')} — потрачено {rub('6 000')}, перерасход {rub('1 000')}" in view
    salary = await preset(session, user, "salary")
    await feed(callback_update(MoneyCb(action="budgetset", id=salary.id).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == STALE


async def test_back_to_the_section(feed, fake, make_user) -> None:
    await make_user()
    await feed(press("home"))
    assert edited(fake).text.startswith("💰 ")
