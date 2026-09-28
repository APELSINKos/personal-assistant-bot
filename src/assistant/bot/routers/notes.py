"""📝 Notes: a paged list with delete buttons and a short dialog to add a note."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import (
    PAGE_SIZE,
    NoteCb,
    cancel_menu,
    main_menu,
    page_buttons,
    paginate,
    preview,
)
from assistant.bot.sections import section
from assistant.bot.states import NoteForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.i18n import Translator
from assistant.core.models import Note
from assistant.core.services import notes


def notes_view(items: list[Note], page: int, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    add = [InlineKeyboardButton(text=t("button-add"), callback_data=NoteCb(action="add").pack())]
    if not items:
        return t("notes-empty"), InlineKeyboardMarkup(inline_keyboard=[add])
    chunk, page, pages = paginate(items, page)
    lines = [t("notes-title", count=len(items), limit=LIMITS.notes), ""]
    rows: list[list[InlineKeyboardButton]] = []
    for number, note in enumerate(chunk, start=page * PAGE_SIZE + 1):
        lines.append(t("list-item", number=number, text=note.text))
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("button-delete-item", number=number, text=preview(note.text, 30)),
                    callback_data=NoteCb(action="del", id=note.id, page=page).pack(),
                )
            ]
        )
    if pages > 1:
        lines += ["", t("page", current=page + 1, total=pages)]
        rows.append(page_buttons(t, page, pages, lambda p: NoteCb(action="page", page=p).pack()))
    rows.append(add)
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _view(ctx: Ctx, page: int) -> tuple[str, InlineKeyboardMarkup]:
    return notes_view(await notes.all_for(ctx.session, ctx.user.id), page, ctx.t)


@section("notes")
async def show_notes(message: Message, ctx: Ctx) -> None:
    text, markup = await _view(ctx, 0)
    await message.answer(text, reply_markup=markup)


async def on_page(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    text, markup = await _view(ctx, callback_data.page)
    await replies.edit(bot, query, text, markup)


async def on_delete(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    removed = await notes.delete(ctx.session, ctx.user.id, callback_data.id)
    await query.answer(ctx.t("deleted" if removed else "already-deleted"))
    text, markup = await _view(ctx, callback_data.page)
    await replies.edit(bot, query, text, markup)


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if await notes.count(ctx.session, ctx.user.id) >= LIMITS.notes:
        await query.answer(ctx.t("notes-limit", limit=LIMITS.notes), show_alert=True)
        return
    await query.answer()
    await ctx.state.set_state(NoteForm.text)
    await ctx.state.set_data({"hint": "hint-note"})
    await replies.send(bot, query, ctx.t("note-ask", limit=LIMITS.note_length), cancel_menu(ctx.t))


async def save_note(message: Message, ctx: Ctx) -> None:
    try:
        await notes.create(ctx.session, ctx.user.id, message.text or "")
    except InvalidInput:
        await message.answer(ctx.t("note-bad-text", limit=LIMITS.note_length))
        return
    except LimitReached:
        await ctx.state.clear()
        await message.answer(
            ctx.t("notes-limit", limit=LIMITS.notes), reply_markup=main_menu(ctx.t)
        )
        return
    await ctx.state.clear()
    await message.answer(ctx.t("note-saved"), reply_markup=main_menu(ctx.t))


def create_router() -> Router:
    router = Router(name="notes")
    router.callback_query.register(on_page, NoteCb.filter(F.action == "page"))
    router.callback_query.register(on_delete, NoteCb.filter(F.action == "del"))
    router.callback_query.register(on_add, NoteCb.filter(F.action == "add"))
    router.message.register(save_note, NoteForm.text, F.text)
    return router
