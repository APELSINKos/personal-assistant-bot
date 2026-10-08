"""💰 Финансы: the month so far, its entries, the budgets, the report picture and the bank's
rates."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import MoneyCb, cancel_menu, main_menu, page_buttons, paginate
from assistant.bot.money_texts import budget_text, entries_text, entry_line, money, section_text
from assistant.bot.routers.rates import send_rates
from assistant.bot.sections import section
from assistant.bot.states import MoneyForm
from assistant.core.errors import InvalidInput, NotFound, UpstreamUnavailable
from assistant.core.money_style import EXPENSE
from assistant.core.services import money as money_service
from assistant.core.services import money_cards, money_month
from assistant.core.services.money_phrases import to_hundredths
from assistant.core.timeutil import SUPPORTED_YEARS, local_today, utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
RATE_LINES = ("USD", "EUR")
ENTRIES_PAGE = 10
DELETE_ROW = 5


def _button(text: str, data: MoneyCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def section_markup(ctx: Ctx) -> InlineKeyboardMarkup:
    t = ctx.t
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(t("button-money-report"), MoneyCb(action="report")),
                _button(t("button-money-entries"), MoneyCb(action="entries")),
            ],
            [
                _button(t("button-money-budget"), MoneyCb(action="budget")),
                _button(t("button-money-rates"), MoneyCb(action="rates")),
            ],
        ]
    )


def _back(ctx: Ctx, data: MoneyCb) -> list[InlineKeyboardButton]:
    return [_button(ctx.t("button-back"), data)]


async def names(ctx: Ctx) -> dict[int, str]:
    """Every category's name in the user's language."""
    found = await money_service.categories(ctx.session, ctx.user)
    return {item.id: money_service.name_of(item, ctx.t) for item in found}


async def _section(ctx: Ctx, now: datetime) -> tuple[str, InlineKeyboardMarkup]:
    month = await money_month.month(ctx.session, ctx.user, now=now)
    return section_text(month, await names(ctx), ctx.user.currency, ctx.t), section_markup(ctx)


@section("money")
async def show_money(message: Message, ctx: Ctx) -> None:
    text, markup = await _section(ctx, clock())
    await message.answer(text, reply_markup=markup)


async def on_home(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *await _section(ctx, clock()))


async def _entries(ctx: Ctx, page: int, now: datetime) -> tuple[str, InlineKeyboardMarkup]:
    """This month's entries, the newest first, ten a page, each with a delete button."""
    today = local_today(ctx.user.timezone, now)
    rows = await money_month.entries(ctx.session, ctx.user, today.replace(day=1))
    chunk, page, pages = paginate(rows, page, ENTRIES_PAGE)
    first = page * ENTRIES_PAGE + 1
    text = entries_text(chunk, first, len(rows), today, await names(ctx), ctx.user.currency, ctx.t)
    if pages > 1:
        text += "\n\n" + ctx.t("page", current=page + 1, total=pages)
    buttons = [
        _button(f"🗑 {number}", MoneyCb(action="delask", id=entry.id, page=page))
        for number, (entry, _) in enumerate(chunk, start=first)
    ]
    keyboard = [buttons[index : index + DELETE_ROW] for index in range(0, len(buttons), DELETE_ROW)]
    paging = page_buttons(ctx.t, page, pages, lambda p: MoneyCb(action="entries", page=p).pack())
    if paging:
        keyboard.append(paging)
    keyboard.append(_back(ctx, MoneyCb(action="home")))
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


async def on_entries(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *await _entries(ctx, callback_data.page, clock()))


async def on_delete_ask(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    page = callback_data.page
    try:
        entry = await money_service.entry(ctx.session, ctx.user, callback_data.id)
    except NotFound:
        await query.answer(ctx.t("already-deleted"))
        await replies.edit(bot, query, *await _entries(ctx, page, clock()))
        return
    category = await money_service.category(ctx.session, ctx.user, entry.category_id)
    name = money_service.name_of(category, ctx.t)
    what = entry_line(entry, category, name, ctx.user.currency, entry.day, ctx.t)
    yes = MoneyCb(action="del", id=entry.id, page=page)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(ctx.t("button-confirm-delete"), yes),
                _button(ctx.t("button-back"), MoneyCb(action="entries", page=page)),
            ]
        ]
    )
    await query.answer()
    await replies.edit(bot, query, ctx.t("money-delete-ask", what=what), markup)


async def on_delete(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    removed = await money_service.delete_entry(ctx.session, ctx.user, callback_data.id)
    await replies.answer_quietly(query, ctx.t("deleted" if removed else "already-deleted"))
    await replies.edit(bot, query, *await _entries(ctx, callback_data.page, clock()))


async def _budget(ctx: Ctx, now: datetime) -> tuple[str, InlineKeyboardMarkup]:
    month = await money_month.month(ctx.session, ctx.user, now=now)
    expenses = await money_service.categories(ctx.session, ctx.user, kind=EXPENSE)
    text = budget_text(month, expenses, await names(ctx), ctx.user.currency, ctx.t)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(ctx.t("button-budget-total"), MoneyCb(action="budgetset")),
                _button(ctx.t("button-budget-categories"), MoneyCb(action="budgetcats")),
            ],
            _back(ctx, MoneyCb(action="home")),
        ]
    )
    return text, markup


async def on_budget(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *await _budget(ctx, clock()))


async def on_budget_categories(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """The expense categories to give a budget, each with its current one."""
    items = await money_service.categories(ctx.session, ctx.user, kind=EXPENSE, visible=True)
    buttons = []
    for item in items:
        label = f"{item.emoji} {money_service.name_of(item, ctx.t)}"
        if item.budget is not None:
            label += f" · {money(item.budget, ctx.user.currency, ctx.t)}"
        buttons.append(_button(label, MoneyCb(action="budgetset", id=item.id)))
    keyboard = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    keyboard.append(_back(ctx, MoneyCb(action="budget")))
    await query.answer()
    await replies.edit(
        bot, query, ctx.t("money-budget-pick"), InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


async def on_budget_set(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    """Ask for the total budget (id 0) or a category's."""
    if callback_data.id:
        try:
            category = await money_service.category(ctx.session, ctx.user, callback_data.id)
        except NotFound:
            await query.answer(ctx.t("already-deleted"))
            return
        if category.kind != EXPENSE:
            await query.answer(ctx.t("stale-button"))
            return
        name = f"{category.emoji} {money_service.name_of(category, ctx.t)}"
        ask = ctx.t("money-budget-ask", name=name)
    else:
        ask = ctx.t("money-budget-ask-total")
    await query.answer()
    await ctx.state.set_state(MoneyForm.budget)
    await ctx.state.set_data({"hint": "hint-money-budget", "category": callback_data.id})
    await replies.send(bot, query, ask, cancel_menu(ctx.t))


def budget_amount(text: str) -> int | None:
    """«30000», «30 000 ₽», «30к», «1,5к» in hundredths; «0» (removing the budget) is 0."""
    cleaned = text.strip().casefold().removesuffix("₽").removesuffix("р").strip()
    if cleaned == "0":
        return 0
    for suffix in ("тыс", "к", "k"):
        if cleaned.endswith(suffix):
            return to_hundredths(cleaned.removesuffix(suffix).strip(), thousands=True)
    return to_hundredths(cleaned)


async def got_budget(message: Message, ctx: Ctx) -> None:
    amount = budget_amount(message.text or "")
    if amount is None:
        await message.answer(ctx.t("money-budget-bad"))
        return
    category_id = int((await ctx.state.get_data()).get("category", 0))
    value = amount or None
    try:
        if category_id:
            await money_service.update_category(ctx.session, ctx.user, category_id, budget=value)
        else:
            await money_service.set_budget(ctx.session, ctx.user, value)
    except NotFound:
        await ctx.state.clear()
        await message.answer(ctx.t("already-deleted"), reply_markup=main_menu(ctx.t))
        return
    except InvalidInput:
        await message.answer(ctx.t("money-budget-bad"))
        return
    await ctx.state.clear()
    saved = ctx.t("money-budget-saved" if value else "money-budget-removed")
    await message.answer(saved, reply_markup=main_menu(ctx.t))
    text, markup = await _budget(ctx, clock())
    await message.answer(text, reply_markup=markup)


def _month(value: str, today: date) -> date | None:
    """The month a report button asks for: «» is this one; a forged or future one is None."""
    if not value:
        return today.replace(day=1)
    try:
        first = datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        return None
    return first if first.year in SUPPORTED_YEARS and first <= today else None


async def on_report(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    """The month as a picture, to forward anywhere; a button under it shows the month before."""
    now = clock()
    today = local_today(ctx.user.timezone, now)
    first = _month(callback_data.value, today)
    if first is None:
        await query.answer(ctx.t("stale-button"))
        return
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    await query.answer()
    month = await money_month.month(ctx.session, ctx.user, first, now=now)
    me = await bot.me()
    report = money_cards.report_for(month, await names(ctx), ctx.user.currency, me.username or "")
    image = await money_cards.draw_report(report, ctx.t)
    previous = (first - timedelta(days=1)).replace(day=1)
    oldest = await money_month.first_month(ctx.session, ctx.user)
    markup = None
    if oldest is not None and oldest <= previous:
        title = money_cards.month_title(previous, ctx.lang)
        data = MoneyCb(action="report", value=previous.strftime("%Y-%m"))
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[_button(ctx.t("button-money-previous", month=title), data)]]
        )
    caption = ctx.t(
        "money-report-caption",
        month=money_cards.month_title(first, ctx.lang),
        amount=money(month.spent, ctx.user.currency, ctx.t),
    )
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="money.jpg"),
        caption=caption,
        reply_markup=markup,
    )


async def on_rates(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await send_rates(bot, ctx.user.id, ctx)


async def on_chart(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """USD and EUR over 30 days as a picture."""
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    await query.answer()
    try:
        lines = tuple([(code, tuple(await ctx.cbr.history(code))) for code in RATE_LINES])
    except (UpstreamUnavailable, LookupError):
        await bot.send_message(ctx.user.id, ctx.t("rates-unavailable"))
        return
    me = await bot.me()
    card = money_cards.RatesCard(lines, local_today(ctx.user.timezone, clock()), me.username or "")
    image = await money_cards.draw_rates(card, ctx.t)
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="rates.jpg"),
        caption=ctx.t("rates-card-caption"),
    )


def create_router() -> Router:
    router = Router(name="money")
    router.message.register(got_budget, MoneyForm.budget, F.text)
    router.callback_query.register(on_home, MoneyCb.filter(F.action == "home"))
    router.callback_query.register(on_entries, MoneyCb.filter(F.action == "entries"))
    router.callback_query.register(on_delete_ask, MoneyCb.filter(F.action == "delask"))
    router.callback_query.register(on_delete, MoneyCb.filter(F.action == "del"))
    router.callback_query.register(on_budget, MoneyCb.filter(F.action == "budget"))
    router.callback_query.register(on_budget_categories, MoneyCb.filter(F.action == "budgetcats"))
    router.callback_query.register(on_budget_set, MoneyCb.filter(F.action == "budgetset"))
    router.callback_query.register(on_report, MoneyCb.filter(F.action == "report"))
    router.callback_query.register(on_rates, MoneyCb.filter(F.action == "rates"))
    router.callback_query.register(on_chart, MoneyCb.filter(F.action == "chart"))
    return router
