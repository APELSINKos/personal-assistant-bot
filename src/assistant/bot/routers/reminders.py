"""⏰ Reminders: a phrase anywhere → a confirmation card, the list with repeats, deletion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import (
    PAGE_SIZE,
    ReminderCb,
    cancel_menu,
    card_markup,
    main_menu,
    page_buttons,
    paginate,
    preview,
    time_choices,
)
from assistant.bot.sections import section
from assistant.bot.states import ReminderForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.i18n import Translator
from assistant.core.models import Reminder, ReminderStatus, User
from assistant.core.services import phrases, reminders
from assistant.core.services.phrases import Parsed
from assistant.core.services.recurrence import describe
from assistant.core.timeutil import to_local, utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
Send = Callable[[str, Any], Awaitable[Any]]


def looks_like_reminder(text: str | None) -> bool:
    """Only the time anchor matters here, so any "now" will do."""
    return text is not None and phrases.parse(text, datetime(2000, 1, 1)) is not None


def _local_now(ctx: Ctx) -> datetime:
    return to_local(clock(), ctx.user.timezone)


def _item_line(number: int, reminder: Reminder, user: User, t: Translator) -> str:
    rule = reminders.rule_of(reminder)
    if rule is not None:
        return t("reminder-item-repeat", number=number, rule=describe(rule, t), text=reminder.text)
    when = texts.short_moment(reminder.due_at, user.timezone, t.lang)
    return t("reminder-item", number=number, when=when, text=reminder.text)


def reminders_view(
    items: list[Reminder],
    page: int,
    user: User,
    t: Translator,
) -> tuple[str, InlineKeyboardMarkup]:
    add = [
        InlineKeyboardButton(text=t("button-add"), callback_data=ReminderCb(action="add").pack())
    ]
    if not items:
        return t("reminders-empty"), InlineKeyboardMarkup(inline_keyboard=[add])
    chunk, page, pages = paginate(items, page)
    lines = [t("reminders-title", count=len(items), limit=LIMITS.reminders), ""]
    rows: list[list[InlineKeyboardButton]] = []
    for number, reminder in enumerate(chunk, start=page * PAGE_SIZE + 1):
        lines.append(_item_line(number, reminder, user, t))
        action = "delask" if reminders.rule_of(reminder) is not None else "del"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("button-delete-item", number=number, text=preview(reminder.text, 30)),
                    callback_data=ReminderCb(action=action, id=reminder.id, page=page).pack(),
                )
            ]
        )
    if pages > 1:
        lines += ["", t("page", current=page + 1, total=pages)]
        rows.append(
            page_buttons(t, page, pages, lambda p: ReminderCb(action="page", page=p).pack())
        )
    rows.append(add)
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _view(ctx: Ctx, page: int) -> tuple[str, InlineKeyboardMarkup]:
    items = await reminders.pending(ctx.session, ctx.user.id)
    return reminders_view(items, page, ctx.user, ctx.t)


@section("reminders")
async def show_reminders(message: Message, ctx: Ctx) -> None:
    text, markup = await _view(ctx, 0)
    await message.answer(text, reply_markup=markup)


async def on_page(query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    text, markup = await _view(ctx, callback_data.page)
    await replies.edit(bot, query, text, markup)


async def on_delete_ask(
    query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot
) -> None:
    reminder = await reminders.get_owned(ctx.session, ctx.user.id, callback_data.id)
    if reminder is None or reminder.status is not ReminderStatus.PENDING:
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        text, markup = await _view(ctx, callback_data.page)
        await replies.edit(bot, query, text, markup)
        return
    await query.answer()
    back = ReminderCb(action="page", page=callback_data.page).pack()
    confirm = ReminderCb(action="del", id=reminder.id, page=callback_data.page).pack()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ctx.t("button-confirm-delete"), callback_data=confirm)],
            [InlineKeyboardButton(text=ctx.t("button-card-cancel"), callback_data=back)],
        ]
    )
    question = ctx.t("reminder-delete-series", text=preview(reminder.text, 60))
    await replies.edit(bot, query, question, markup)


async def on_delete(query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot) -> None:
    removed = await reminders.cancel(ctx.session, ctx.user.id, callback_data.id)
    await replies.answer_quietly(query, ctx.t("deleted" if removed else "already-deleted"))
    text, markup = await _view(ctx, callback_data.page)
    await replies.edit(bot, query, text, markup)


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if await reminders.count_pending(ctx.session, ctx.user.id) >= LIMITS.reminders:
        await query.answer(ctx.t("reminders-limit", limit=LIMITS.reminders), show_alert=True)
        return
    await query.answer()
    await ctx.state.set_state(ReminderForm.text)
    await ctx.state.set_data({"hint": "hint-reminder-phrase"})
    await replies.send(bot, query, ctx.t("reminder-ask-phrase"), cancel_menu(ctx.t))


async def _ask_time(send: Send, ctx: Ctx, parsed: Parsed, local_now: datetime) -> None:
    await ctx.state.set_state(ReminderForm.time)
    await ctx.state.set_data(
        {"parsed": phrases.dump(parsed), "at": local_now.isoformat(), "hint": "hint-reminder-time"}
    )
    await send(ctx.t("reminder-ask-time"), time_choices(ctx.t))


async def _offer(send: Send, ctx: Ctx, parsed: Parsed, local_now: datetime) -> None:
    """Show the card, or ask for what the phrase is missing."""
    if not parsed.text.strip():
        await ctx.state.set_state(ReminderForm.text)
        await ctx.state.set_data({"hint": "hint-reminder-phrase"})
        await send(ctx.t("reminder-need-text"), None)
        return
    if parsed.needs_time:
        await _ask_time(send, ctx, parsed, local_now)
        return
    when = parsed.when(local_now)
    if when is not None and when <= local_now.replace(tzinfo=None):
        await send(ctx.t("reminder-past"), None)
        await _ask_time(send, ctx, parsed, local_now)
        return
    await ctx.state.set_state(ReminderForm.confirm)
    await ctx.state.set_data({"parsed": phrases.dump(parsed), "at": local_now.isoformat()})
    await send(texts.card_text(parsed, local_now, ctx.t), card_markup(ctx.t))


def _answer(message: Message) -> Send:
    return lambda text, markup: message.answer(text, reply_markup=markup)


def _send_to(bot: Bot, query: CallbackQuery) -> Send:
    return lambda text, markup: replies.send(bot, query, text, markup)


async def phrase_anywhere(message: Message, ctx: Ctx) -> None:
    local_now = _local_now(ctx)
    parsed = phrases.parse(message.text or "", local_now)
    if parsed is not None:
        await _offer(_answer(message), ctx, parsed, local_now)


async def got_phrase(message: Message, ctx: Ctx) -> None:
    local_now = _local_now(ctx)
    parsed = phrases.parse(message.text or "", local_now)
    if parsed is None:
        await message.answer(ctx.t("reminder-not-understood"))
        return
    await _offer(_answer(message), ctx, parsed, local_now)


async def _stored(ctx: Ctx) -> Parsed | None:
    data = await ctx.state.get_data()
    raw = data.get("parsed")
    return phrases.load(raw) if isinstance(raw, dict) else None


async def got_time(message: Message, ctx: Ctx) -> None:
    base = await _stored(ctx)
    local_now = _local_now(ctx)
    text = (message.text or "").strip()
    answer = phrases.parse(text, local_now) or phrases.parse(f"в {text}", local_now)
    if base is None or answer is None or phrases.merge(base, answer).needs_time:
        await message.answer(ctx.t("reminder-ask-time"), reply_markup=time_choices(ctx.t))
        return
    await _offer(_answer(message), ctx, phrases.merge(base, answer), local_now)


async def on_time_choice(
    query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot
) -> None:
    base = await _stored(ctx)
    if base is None:
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    await _offer(_send_to(bot, query), ctx, base.with_time(callback_data.value), _local_now(ctx))


async def on_create(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    data = await ctx.state.get_data()
    raw, at = data.get("parsed"), data.get("at")
    if not isinstance(raw, dict) or not isinstance(at, str):
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        await replies.drop_buttons(bot, query)
        return
    parsed, card_now = phrases.load(raw), datetime.fromisoformat(at)
    send = _send_to(bot, query)
    try:
        # The card's own "now": «через 20 минут» means what the card showed.
        reminder = await reminders.create_from(ctx.session, ctx.user, parsed, card_now)
    except LimitReached:
        await ctx.state.clear()
        await replies.answer_quietly(query)
        await replies.drop_buttons(bot, query)
        await send(ctx.t("reminders-limit", limit=LIMITS.reminders), main_menu(ctx.t))
        return
    except InvalidInput:
        await replies.answer_quietly(query)
        await replies.drop_buttons(bot, query)
        await send(ctx.t("reminder-past"), None)
        await _ask_time(send, ctx, parsed, _local_now(ctx))
        return
    await ctx.state.clear()
    await replies.answer_quietly(query)
    await replies.drop_buttons(bot, query)
    await send(texts.saved_text(reminder, ctx.user.timezone, card_now, ctx.t), main_menu(ctx.t))


async def on_retime(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    base = await _stored(ctx)
    if base is None:
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        await replies.drop_buttons(bot, query)
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    await _ask_time(_send_to(bot, query), ctx, base, _local_now(ctx))


async def on_card_cancel(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await ctx.state.clear()
    await replies.answer_quietly(query)
    await replies.drop_buttons(bot, query)
    await replies.send(bot, query, ctx.t("cancelled"), main_menu(ctx.t))


def create_router() -> Router:
    router = Router(name="reminders")
    router.callback_query.register(on_page, ReminderCb.filter(F.action == "page"))
    router.callback_query.register(on_delete_ask, ReminderCb.filter(F.action == "delask"))
    router.callback_query.register(on_delete, ReminderCb.filter(F.action == "del"))
    router.callback_query.register(on_add, ReminderCb.filter(F.action == "add"))
    router.callback_query.register(on_create, ReminderCb.filter(F.action == "ok"))
    router.callback_query.register(on_retime, ReminderCb.filter(F.action == "retime"))
    router.callback_query.register(on_card_cancel, ReminderCb.filter(F.action == "no"))
    router.callback_query.register(
        on_time_choice, ReminderForm.time, ReminderCb.filter(F.action == "t")
    )
    router.message.register(got_phrase, ReminderForm.text, F.text)
    router.message.register(got_phrase, ReminderForm.confirm, F.text)  # a new phrase, a new card
    router.message.register(got_time, ReminderForm.time, F.text)
    router.message.register(phrase_anywhere, StateFilter(None), F.text.func(looks_like_reminder))
    return router
