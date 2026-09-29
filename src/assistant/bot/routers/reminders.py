"""⏰ Reminders: a paged list with cancel buttons and a two-step dialog (text → time)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import (
    PAGE_SIZE,
    ReminderCb,
    cancel_menu,
    main_menu,
    page_buttons,
    paginate,
    preview,
)
from assistant.bot.sections import section
from assistant.bot.states import ReminderForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.i18n import Translator
from assistant.core.models import Reminder, User
from assistant.core.services import reminders
from assistant.core.timeutil import now_local, to_local


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
        when = texts.short_moment(reminder.due_at, user.timezone, t.lang)
        lines.append(t("reminder-item", number=number, when=when, text=reminder.text))
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("button-delete-item", number=number, text=preview(reminder.text, 30)),
                    callback_data=ReminderCb(action="del", id=reminder.id, page=page).pack(),
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
    await ctx.state.set_data({"hint": "hint-reminder-text"})
    await replies.send(
        bot, query, ctx.t("reminder-ask-text", limit=LIMITS.reminder_length), cancel_menu(ctx.t)
    )


async def got_text(message: Message, ctx: Ctx) -> None:
    try:
        text = reminders.clean_text(message.text or "")
    except InvalidInput:
        await message.answer(ctx.t("reminder-bad-text", limit=LIMITS.reminder_length))
        return
    await ctx.state.set_state(ReminderForm.when)
    await ctx.state.set_data({"text": text, "hint": "hint-when"})
    await message.answer(ctx.t("reminder-ask-when"))


async def got_when(message: Message, ctx: Ctx) -> None:
    text = (await ctx.state.get_data()).get("text")
    if not isinstance(text, str):
        await ctx.state.clear()
        await message.answer(ctx.t("unknown"), reply_markup=main_menu(ctx.t))
        return
    local_now = now_local(ctx.user.timezone)
    when = reminders.parse_when(message.text or "", local_now)
    if when is None:
        await message.answer(ctx.t("reminder-bad-when"))
        return
    try:
        reminder = await reminders.create(ctx.session, ctx.user, text, when)
    except InvalidInput as error:
        # "invalid": a date parse_when let through that still has no place in time.
        unusable = error.params.get("reason") == "invalid"
        await message.answer(ctx.t("reminder-bad-when" if unusable else "reminder-past"))
        return
    except LimitReached:
        await ctx.state.clear()
        await message.answer(
            ctx.t("reminders-limit", limit=LIMITS.reminders), reply_markup=main_menu(ctx.t)
        )
        return
    await ctx.state.clear()
    local = to_local(reminder.due_at, ctx.user.timezone)
    await message.answer(
        ctx.t(
            "reminder-saved",
            date=texts.long_day(local.date(), ctx.lang, local_now.year),
            time=local.strftime("%H:%M"),
            text=reminder.text,
        ),
        reply_markup=main_menu(ctx.t),
    )


def create_router() -> Router:
    router = Router(name="reminders")
    router.callback_query.register(on_page, ReminderCb.filter(F.action == "page"))
    router.callback_query.register(on_delete, ReminderCb.filter(F.action == "del"))
    router.callback_query.register(on_add, ReminderCb.filter(F.action == "add"))
    router.message.register(got_text, ReminderForm.text, F.text)
    router.message.register(got_when, ReminderForm.when, F.text)
    return router
