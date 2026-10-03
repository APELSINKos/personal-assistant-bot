"""«кофе 250» anywhere in the chat: the entry is noted at once, with buttons to move it to
another category (or kind) and to undo it. Reminder phrases are checked first (routers order)."""

from __future__ import annotations

from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import EntryCb, cancel_menu, main_menu
from assistant.bot.money_texts import alert_text, entry_line, entry_text
from assistant.bot.states import MoneyForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import MoneyCategory, MoneyEntry
from assistant.core.money_style import CATEGORY_EMOJI, CURRENCIES, EXPENSE, INCOME, KINDS
from assistant.core.services import money, money_month
from assistant.core.services.money_month import Alert
from assistant.core.services.money_phrases import OtherCurrency, Quick, parse_quick
from assistant.core.timeutil import local_today

EMOJI_ROW = 8


def looks_like_money(text: str | None) -> bool:
    """A phrase with an amount in any currency (the user's is checked in the handler); a command
    with a number («/note 7») is never one."""
    if text is None or text.lstrip().startswith("/"):
        return False
    return parse_quick(text, "RUB") is not None


def _button(text: str, data: EntryCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def entry_markup(entry: MoneyEntry, ctx: Ctx) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(ctx.t("button-entry-category"), EntryCb(action="cat", id=entry.id)),
                _button(ctx.t("button-entry-undo"), EntryCb(action="undo", id=entry.id)),
            ]
        ]
    )


async def _card(ctx: Ctx, entry: MoneyEntry) -> tuple[str, InlineKeyboardMarkup]:
    category = await money.category(ctx.session, ctx.user, entry.category_id)
    month = await money_month.month(ctx.session, ctx.user, entry.day)
    name = money.name_of(category, ctx.t)
    text = entry_text(entry, category, name, month, ctx.user.currency, ctx.t)
    return text, entry_markup(entry, ctx)


async def _send_alerts(bot: Bot, ctx: Ctx, entry: MoneyEntry, alerts: list[Alert]) -> None:
    first = entry.day.replace(day=1)
    for alert in alerts:
        name = None if alert.category is None else money.name_of(alert.category, ctx.t)
        await bot.send_message(
            ctx.user.id, alert_text(alert, name, first, ctx.user.currency, ctx.t)
        )


async def quick_entry(message: Message, ctx: Ctx, bot: Bot) -> None:
    found = parse_quick(message.text or "", ctx.user.currency)
    if found is None:  # the filter's reading in roubles found money, this one does not
        await message.answer(ctx.t("unknown"), reply_markup=main_menu(ctx.t))
        return
    if isinstance(found, OtherCurrency):
        sign = CURRENCIES[ctx.user.currency].sign
        await message.answer(ctx.t("money-other-currency", sign=sign))
        return
    entry = await _note(message, ctx, found)
    if entry is None:
        return
    text, markup = await _card(ctx, entry)
    await message.answer(text, reply_markup=markup)
    await _send_alerts(
        bot, ctx, entry, await money_month.alerts_after(ctx.session, ctx.user, entry)
    )


async def _note(message: Message, ctx: Ctx, quick: Quick) -> MoneyEntry | None:
    category = await money.guess_category(ctx.session, ctx.user, quick)
    day = local_today(ctx.user.timezone) - timedelta(days=quick.days_ago)
    try:
        return await money.add_entry(
            ctx.session,
            ctx.user,
            amount=quick.amount,
            category_id=category.id,
            note=quick.note,
            day=day,
        )
    except LimitReached as error:
        key = "money-limit-month" if error.params.get("entity") == "entry_month" else "money-limit"
        await message.answer(ctx.t(key, limit=error.params.get("limit", 0)))
    except InvalidInput:
        await message.answer(ctx.t("money-bad-note", limit=LIMITS.money_note_length))
    return None


async def _gone(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer(ctx.t("already-deleted"))
    await replies.drop_buttons(bot, query)


async def _picker(ctx: Ctx, entry: MoneyEntry, kind: str) -> tuple[str, InlineKeyboardMarkup]:
    """The categories of one kind to move the entry to, the other kind, a new category."""
    items = await money.categories(ctx.session, ctx.user, kind=kind, visible=True)
    buttons = [
        _button(
            ("✓ " if item.id == entry.category_id else "")
            + f"{item.emoji} {money.name_of(item, ctx.t)}",
            EntryCb(action="set", id=entry.id, value=item.id),
        )
        for item in items
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    other = INCOME if kind == EXPENSE else EXPENSE
    rows.append(
        [
            _button(
                ctx.t("button-entry-income" if other == INCOME else "button-entry-expense"),
                EntryCb(action="kind", id=entry.id, value=KINDS.index(other)),
            ),
            _button(
                ctx.t("button-entry-new"),
                EntryCb(action="new", id=entry.id, value=KINDS.index(kind)),
            ),
        ]
    )
    rows.append([_button(ctx.t("button-back"), EntryCb(action="back", id=entry.id))])
    text = ctx.t("money-pick", note=entry.note) if entry.note else ctx.t("money-pick-plain")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _owned(query: CallbackQuery, data: EntryCb, ctx: Ctx, bot: Bot) -> MoneyEntry | None:
    try:
        return await money.entry(ctx.session, ctx.user, data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return None


async def on_pick(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    entry = await _owned(query, callback_data, ctx, bot)
    if entry is None:
        return
    category = await money.category(ctx.session, ctx.user, entry.category_id)
    await query.answer()
    await replies.edit(bot, query, *await _picker(ctx, entry, category.kind))


async def on_kind(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    entry = await _owned(query, callback_data, ctx, bot)
    if entry is None:
        return
    if callback_data.value >= len(KINDS):
        await query.answer(ctx.t("stale-button"))
        return
    await query.answer()
    await replies.edit(bot, query, *await _picker(ctx, entry, KINDS[callback_data.value]))


async def on_set(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    """Move the entry; the next entry with this note goes to this category too."""
    try:
        entry = await money.update_entry(
            ctx.session, ctx.user, callback_data.id, category_id=callback_data.value
        )
    except NotFound:
        await _gone(query, ctx, bot)
        return
    if entry.note:
        await money.remember(ctx.session, ctx.user, entry.note, entry.category_id)
    await replies.answer_quietly(query)  # the move is done: an expired query must not hide it
    await replies.edit(bot, query, *await _card(ctx, entry))
    await _send_alerts(
        bot, ctx, entry, await money_month.alerts_after(ctx.session, ctx.user, entry)
    )


async def on_back(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    entry = await _owned(query, callback_data, ctx, bot)
    if entry is None:
        return
    await query.answer()
    await replies.edit(bot, query, *await _card(ctx, entry))


async def on_undo(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    entry = await _owned(query, callback_data, ctx, bot)
    if entry is None:
        return
    category = await money.category(ctx.session, ctx.user, entry.category_id)
    today = local_today(ctx.user.timezone)
    what = entry_line(
        entry, category, money.name_of(category, ctx.t), ctx.user.currency, today, ctx.t
    )
    await money.delete_entry(ctx.session, ctx.user, entry.id)
    await replies.answer_quietly(query)
    await replies.edit(bot, query, ctx.t("money-undone", what=what))


async def on_new(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    """A new category for the entry: its name now, then its emoji."""
    entry = await _owned(query, callback_data, ctx, bot)
    if entry is None:
        return
    if callback_data.value >= len(KINDS):
        await query.answer(ctx.t("stale-button"))
        return
    await query.answer()
    await ctx.state.set_state(MoneyForm.category)
    await ctx.state.set_data(
        {"hint": "hint-money-category", "entry": entry.id, "kind": KINDS[callback_data.value]}
    )
    ask = ctx.t("money-new-ask", limit=LIMITS.money_category_length)
    await replies.send(bot, query, ask, cancel_menu(ctx.t))


def _emoji_markup(entry_id: int) -> InlineKeyboardMarkup:
    buttons = [
        _button(emoji, EntryCb(action="emoji", id=entry_id, value=index))
        for index, emoji in enumerate(CATEGORY_EMOJI)
    ]
    rows = [buttons[index : index + EMOJI_ROW] for index in range(0, len(buttons), EMOJI_ROW)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def got_name(message: Message, ctx: Ctx) -> None:
    data = await ctx.state.get_data()
    try:
        name = await money.check_name(ctx.session, ctx.user, str(data["kind"]), message.text or "")
    except InvalidInput as error:
        key = "money-duplicate" if error.params.get("reason") == "duplicate" else "money-bad-name"
        await message.answer(ctx.t(key, limit=LIMITS.money_category_length))
        return
    await ctx.state.update_data(name=name)
    await message.answer(
        ctx.t("money-new-emoji", name=name), reply_markup=_emoji_markup(int(data["entry"]))
    )


async def on_emoji(query: CallbackQuery, callback_data: EntryCb, ctx: Ctx, bot: Bot) -> None:
    """The new category is made with this emoji, and the entry moves to it."""
    data = await ctx.state.get_data()
    if (
        await ctx.state.get_state() != MoneyForm.category.state
        or data.get("entry") != callback_data.id
        or "name" not in data
        or callback_data.value >= len(CATEGORY_EMOJI)
    ):
        await query.answer(ctx.t("stale-button"))
        return
    await ctx.state.clear()
    try:
        created = await money.create_category(
            ctx.session, ctx.user, str(data["kind"]), str(data["name"]),
            CATEGORY_EMOJI[callback_data.value],
        )  # fmt: skip
    except LimitReached:
        await replies.answer_quietly(query)  # the dialog is over either way
        await replies.send(
            bot,
            query,
            ctx.t("money-categories-full", limit=LIMITS.money_categories),
            main_menu(ctx.t),
        )
        return
    except InvalidInput:  # the same name was taken meanwhile
        await replies.answer_quietly(query)
        await replies.send(bot, query, ctx.t("money-duplicate-late"), main_menu(ctx.t))
        return
    await replies.answer_quietly(query)
    await replies.send(bot, query, _created_text(created, ctx), main_menu(ctx.t))
    try:
        entry = await money.update_entry(
            ctx.session, ctx.user, callback_data.id, category_id=created.id
        )
    except NotFound:
        return  # undone meanwhile: the category stays
    if entry.note:
        await money.remember(ctx.session, ctx.user, entry.note, created.id)
    await replies.edit(bot, query, *await _card(ctx, entry))
    await _send_alerts(
        bot, ctx, entry, await money_month.alerts_after(ctx.session, ctx.user, entry)
    )


def _created_text(category: MoneyCategory, ctx: Ctx) -> str:
    return ctx.t(
        "money-category-created", emoji=category.emoji, name=money.name_of(category, ctx.t)
    )


def create_router() -> Router:
    router = Router(name="money_entry")
    router.message.register(got_name, MoneyForm.category, F.text)
    router.message.register(quick_entry, StateFilter(None), F.text.func(looks_like_money))
    router.callback_query.register(on_pick, EntryCb.filter(F.action == "cat"))
    router.callback_query.register(on_kind, EntryCb.filter(F.action == "kind"))
    router.callback_query.register(on_set, EntryCb.filter(F.action == "set"))
    router.callback_query.register(on_back, EntryCb.filter(F.action == "back"))
    router.callback_query.register(on_undo, EntryCb.filter(F.action == "undo"))
    router.callback_query.register(on_new, EntryCb.filter(F.action == "new"))
    router.callback_query.register(on_emoji, EntryCb.filter(F.action == "emoji"))
    return router
