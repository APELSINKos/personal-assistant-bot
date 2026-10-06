"""📝 Notes: the list, pinned ones on top and then the newest; a note's card with its checklist, its
pin and a delete that asks first; a short dialog to add a note."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import (
    PAGE_SIZE,
    NoteCb,
    NoteItemCb,
    cancel_menu,
    main_menu,
    page_buttons,
    paginate,
    preview,
)
from assistant.bot.replies import NO_PREVIEW
from assistant.bot.sections import section
from assistant.bot.states import NoteForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.i18n import Translator
from assistant.core.services import notes
from assistant.core.services.notes import Item, NoteView
from assistant.core.timeutil import utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
# How much of a text each place shows, in characters: a note's line in the list; its button and
# the delete question; an item's line and button on the card. At 40 an item's line keeps the
# fullest card, 500 characters of text and 20 items, within TEXT_LIMIT, so a card is never cut.
LINE_PREVIEW = 100
BUTTON_PREVIEW = 30
ITEM_PREVIEW = 40

View = tuple[str, InlineKeyboardMarkup]


def _button(text: str, data: NoteCb | NoteItemCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def note_line(number: int, note: NoteView, limit: int, t: Translator) -> str:
    """«1. 📌 Пароль от wifi: hunter2», «2. Покупки ✅ 2/5»: a note on one line, its text cut to
    `limit` characters, with a checklist's progress."""
    text = preview(note.text, limit)
    if note.items:
        text = t("note-progress", text=text, done=note.done, total=note.total)
    return t("note-line-pinned" if note.pinned else "note-line", number=number, text=text)


def notes_view(items: list[NoteView], page: int, t: Translator) -> View:
    """Five notes a page, numbered through the pages; a note's button opens its card."""
    add = _button(t("button-add-note"), NoteCb(action="add"))
    if not items:
        return t("notes-empty"), InlineKeyboardMarkup(inline_keyboard=[[add]])
    chunk, page, pages = paginate(items, page)
    lines = [t("notes-title", count=len(items), limit=LIMITS.notes), ""]
    rows: list[list[InlineKeyboardButton]] = []
    for number, note in enumerate(chunk, start=page * PAGE_SIZE + 1):
        lines.append(note_line(number, note, LINE_PREVIEW, t))
        label = note_line(number, note, BUTTON_PREVIEW, t)
        rows.append([_button(label, NoteCb(action="open", id=note.id, page=page))])
    rows.append([add])
    if pages > 1:
        lines += ["", t("page", current=page + 1, total=pages)]
        rows.append(page_buttons(t, page, pages, lambda p: NoteCb(action="page", page=p).pack()))
    # Lines of 100 characters keep even five pinned checklists of emoji within TEXT_LIMIT.
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _item_line(item: Item, t: Translator) -> str:
    return t("item-done" if item.done else "item-open", text=preview(item.text, ITEM_PREVIEW))


def card_view(note: NoteView, page: int, t: Translator) -> View:
    """A note's card: its text whole, then its items. An item's button checks an open item and
    unchecks a checked one. `page` is where «↩️ К заметкам» leads; every button carries it."""
    text = t("note-card-pinned", text=note.text) if note.pinned else note.text
    items = [_item_line(item, t) for item in note.items]
    if items:
        text += "\n\n" + "\n".join(items)
    rows = [
        [_button(line, NoteItemCb(note=note.id, id=item.id, done=0 if item.done else 1))]
        for item, line in zip(note.items, items, strict=True)
    ]
    own = note.id
    tools: list[InlineKeyboardButton] = []
    if note.done:
        tools.append(_button(t("button-clear-done"), NoteCb(action="clear", id=own, page=page)))
    if tools:
        rows.append(tools)
    pin = "unpin" if note.pinned else "pin"
    rows.append([_button(t(f"button-{pin}"), NoteCb(action=pin, id=own, page=page))])
    rows.append(
        [
            _button(t("button-delete-note"), NoteCb(action="delask", id=own, page=page)),
            _button(t("button-back-notes"), NoteCb(action="page", page=page)),
        ]
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_view(note: NoteView, page: int, t: Translator) -> View:
    """«Удалить?» in place of the card; «↩️ Назад» brings the card back."""
    question = t("note-delete-ask", text=preview(note.text, BUTTON_PREVIEW))
    row = [
        _button(t("button-confirm-delete"), NoteCb(action="delyes", id=note.id, page=page)),
        _button(t("button-back"), NoteCb(action="open", id=note.id, page=page)),
    ]
    return question, InlineKeyboardMarkup(inline_keyboard=[row])


async def _list(ctx: Ctx, page: int) -> View:
    return notes_view(await notes.list_for(ctx.session, ctx.user.id), page, ctx.t)


async def _card(ctx: Ctx, note_id: int) -> View | None:
    """The note's card, or None when the note is gone. Its buttons lead back to the page the note
    is on now: a pin, or notes added in the app, move it from the page it was opened on."""
    for position, note in enumerate(await notes.list_for(ctx.session, ctx.user.id)):
        if note.id == note_id:
            return card_view(note, position // PAGE_SIZE, ctx.t)
    return None


async def _edit(bot: Bot, query: CallbackQuery, view: View) -> None:
    # Notes keep links written out, «тут (https://…)»: no preview card under the list or a card.
    await replies.edit(bot, query, *view, link_preview_options=NO_PREVIEW)


async def _gone(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """The note of the button was deleted, here or in the app: say so and show the list."""
    await replies.answer_quietly(query, ctx.t("already-deleted"))
    await _edit(bot, query, await _list(ctx, 0))


async def _show_card(
    query: CallbackQuery, ctx: Ctx, bot: Bot, note_id: int, answer: str | None = None
) -> None:
    """The note's card in the button's message, after what the button changed."""
    view = await _card(ctx, note_id)
    if view is None:
        await _gone(query, ctx, bot)
        return
    await replies.answer_quietly(query, answer)
    await _edit(bot, query, view)


@section("notes")
async def show_notes(message: Message, ctx: Ctx) -> None:
    text, markup = await _list(ctx, 0)
    await message.answer(text, reply_markup=markup, link_preview_options=NO_PREVIEW)


async def on_page(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await _edit(bot, query, await _list(ctx, callback_data.page))


async def on_open(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    await _show_card(query, ctx, bot, callback_data.id)


async def on_item(query: CallbackQuery, callback_data: NoteItemCb, ctx: Ctx, bot: Bot) -> None:
    """Give the item the state its button carries; a second tap changes nothing more. An item
    deleted in the app meanwhile: «Этого уже нет» and the note's fresh card; the whole note
    deleted: «Этого уже нет» and the list."""
    answer = None
    try:
        await notes.set_item(
            ctx.session, ctx.user.id, callback_data.note, callback_data.id, callback_data.done == 1
        )
    except NotFound as error:
        if error.params.get("entity") != "note_item":
            await _gone(query, ctx, bot)
            return
        answer = ctx.t("already-deleted")
    await _show_card(query, ctx, bot, callback_data.note, answer)


async def on_pin(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    # Pinning a pinned note (an old card, or pinned in the app) changes nothing, unpinning
    # likewise: the card then shows the pin as it is.
    try:
        await notes.set_pinned(
            ctx.session, ctx.user.id, callback_data.id, callback_data.action == "pin", clock()
        )
    except NotFound:
        await _gone(query, ctx, bot)
        return
    except LimitReached:
        await query.answer(ctx.t("pinned-limit", limit=LIMITS.pinned_notes), show_alert=True)
        return
    await _show_card(query, ctx, bot, callback_data.id)


async def on_clear(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        await notes.clear_done(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    await _show_card(query, ctx, bot, callback_data.id)


async def on_delete_ask(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        note = await notes.get_view(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    await query.answer()
    await _edit(bot, query, confirm_view(note, callback_data.page, ctx.t))


async def on_delete(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    if not await notes.delete(ctx.session, ctx.user.id, callback_data.id):
        await _gone(query, ctx, bot)
        return
    await replies.answer_quietly(query, ctx.t("deleted"))
    # Where «↩️ К заметкам» led: the note's page, or the last page left when it was alone there.
    await _edit(bot, query, await _list(ctx, callback_data.page))


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if await notes.count(ctx.session, ctx.user.id) >= LIMITS.notes:
        await query.answer(ctx.t("notes-limit", limit=LIMITS.notes), show_alert=True)
        return
    await query.answer()
    await ctx.state.set_state(NoteForm.text)
    await ctx.state.set_data({"hint": "hint-note"})
    await replies.send(bot, query, ctx.t("note-ask", limit=LIMITS.note_length), cancel_menu(ctx.t))


async def save_note(message: Message, ctx: Ctx) -> None:
    # A note keeps only text, so a hidden link is written out as «words (address)»; the length
    # limit holds for the text with its addresses.
    text = notes.expand_links(message.text or "", message.entities)
    try:
        await notes.create(ctx.session, ctx.user.id, text, now=clock())
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
    for actions, handler in (
        (("page",), on_page),
        (("open",), on_open),
        (("pin", "unpin"), on_pin),
        (("clear",), on_clear),
        (("delask", "del"), on_delete_ask),
        (("delyes",), on_delete),
        (("add",), on_add),
    ):
        router.callback_query.register(handler, NoteCb.filter(F.action.in_(actions)))
    router.callback_query.register(on_item, NoteItemCb.filter())
    router.message.register(save_note, NoteForm.text, F.text)
    return router
