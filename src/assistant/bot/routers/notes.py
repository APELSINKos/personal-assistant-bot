"""📝 Notes: the list, pinned ones on top and then the newest; a note's card with its checklist, its
pin and a delete that asks first; dialogs to add a note or a checklist, to edit a note's text, to
add items and to search the notes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.state import State
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
# An item too long to keep is named by its first characters, so the user finds the line.
ITEM_QUOTE = 20
# A search outlives its dialog in the dialog data: its words and the message with its results.
# Only there do the results' buttons apply it. The menu, /start, /cancel, any new dialog and the
# cleanup of old dialogs drop it with the rest of the data; «✖️ Сбросить поиск» and a search
# that finds nothing any more drop it alone.
QUERY = "notes_query"
QUERY_MESSAGE = "notes_query_message"

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


def _numbered(
    found: list[NoteView], page: int, title: str, actions: tuple[str, str], t: Translator
) -> tuple[str, list[list[InlineKeyboardButton]], list[InlineKeyboardButton]]:
    """A page of notes under `title`, numbered through the pages: the text, a button for each
    note and the ◀️ ▶️ row, empty when there is one page. `actions` open a note and turn a page."""
    open_note, turn = actions
    chunk, page, pages = paginate(found, page)
    lines = [title, ""]
    rows: list[list[InlineKeyboardButton]] = []
    for number, note in enumerate(chunk, start=page * PAGE_SIZE + 1):
        lines.append(note_line(number, note, LINE_PREVIEW, t))
        label = note_line(number, note, BUTTON_PREVIEW, t)
        rows.append([_button(label, NoteCb(action=open_note, id=note.id, page=page))])
    turns: list[InlineKeyboardButton] = []
    if pages > 1:
        lines += ["", t("page", current=page + 1, total=pages)]
        turns = page_buttons(t, page, pages, lambda p: NoteCb(action=turn, page=p).pack())
    # Lines of 100 characters keep even five pinned checklists of emoji within TEXT_LIMIT.
    return "\n".join(lines), rows, turns


def notes_view(items: list[NoteView], page: int, t: Translator) -> View:
    """Five notes a page, numbered through the pages; a note's button opens its card."""
    new = [
        _button(t("button-add-note"), NoteCb(action="add")),
        _button(t("button-add-list"), NoteCb(action="checklist")),
    ]
    if not items:
        return t("notes-empty"), InlineKeyboardMarkup(inline_keyboard=[new])
    title = t("notes-title", count=len(items), limit=LIMITS.notes)
    text, rows, turns = _numbered(items, page, title, ("open", "page"), t)
    rows.append([*new, _button(t("button-find"), NoteCb(action="find"))])
    if turns:
        rows.append(turns)
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def results_view(found: list[NoteView], search: str, page: int, t: Translator) -> View:
    """What a search found, numbered from 1 like the list; a note's button opens its card, which
    leads back here. Nothing to add or search again: «✖️ Сбросить поиск» brings the list back."""
    title = t("search-title", query=search, count=len(found))
    text, rows, turns = _numbered(found, page, title, ("fopen", "fpage"), t)
    if turns:
        rows.append(turns)
    rows.append([_button(t("button-reset-search"), NoteCb(action="reset"))])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _item_line(item: Item, t: Translator) -> str:
    return t("item-done" if item.done else "item-open", text=preview(item.text, ITEM_PREVIEW))


def card_view(note: NoteView, page: int, t: Translator, *, results: bool = False) -> View:
    """A note's card: its text whole, then its items. An item's button checks an open item and
    unchecks a checked one. `page` is where «↩️ К заметкам» leads, a page of a search's results
    when the card is shown in their message (`results`); every button carries it."""
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
    if note.total < LIMITS.note_items:
        tools.append(_button(t("button-add-items"), NoteCb(action="items", id=own, page=page)))
    if note.done:
        tools.append(_button(t("button-clear-done"), NoteCb(action="clear", id=own, page=page)))
    if tools:
        rows.append(tools)
    pin = "unpin" if note.pinned else "pin"
    rows.append(
        [
            _button(t(f"button-{pin}"), NoteCb(action=pin, id=own, page=page)),
            _button(t("button-edit"), NoteCb(action="edit", id=own, page=page)),
        ]
    )
    back = NoteCb(action="fpage" if results else "page", page=page)
    rows.append(
        [
            _button(t("button-delete-note"), NoteCb(action="delask", id=own, page=page)),
            _button(t("button-back-notes"), back),
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


def split_list(text: str) -> tuple[str, list[str]]:
    """A «☑️ Список» message: its first line with words is the title, kept as written (a marker
    there stays), and the lines after it are the items."""
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if line.strip():
            return line.strip(), notes.parse_item_lines("\n".join(lines[number + 1 :]))
    return "", []


def _too_long(items: list[str], t: Translator) -> str | None:
    """The answer to an item longer than an item keeps, quoting its start; None when all fit."""
    for item in items:
        if len(item) > LIMITS.note_item_length:
            quote = item[:ITEM_QUOTE].rstrip() + "…"
            return t("item-too-long", text=quote, limit=LIMITS.note_item_length)
    return None


def _list_refusal(title: str, items: list[str], t: Translator) -> str | None:
    """Why a «☑️ Список» message cannot be saved, in the order a note is checked: the title, the
    items, how many of them; None when it can."""
    if not 1 <= len(title) <= LIMITS.note_length:
        return t("note-bad-text", limit=LIMITS.note_length)
    if not items:
        return t("list-need-item")
    if (too_long := _too_long(items, t)) is not None:
        return too_long
    if len(items) > LIMITS.note_items:
        return t("list-too-long", limit=LIMITS.note_items)
    return None


async def _search_here(ctx: Ctx, query: CallbackQuery) -> str | None:
    """The search whose results the button's message shows, or None: in any other message, and
    once the search is dropped, the buttons of its results work as the list's."""
    data = await ctx.state.get_data()
    search = data.get(QUERY)
    if not isinstance(search, str) or query.message is None:
        return None
    return search if data.get(QUERY_MESSAGE) == query.message.message_id else None


async def _drop_search(ctx: Ctx) -> None:
    data = await ctx.state.get_data()
    data.pop(QUERY, None)
    data.pop(QUERY_MESSAGE, None)
    await ctx.state.set_data(data)


async def _list(ctx: Ctx, page: int) -> View:
    return notes_view(await notes.list_for(ctx.session, ctx.user.id), page, ctx.t)


async def _card(ctx: Ctx, note_id: int, page: int = 0, search: str | None = None) -> View | None:
    """The note's card, or None when the note is gone. Its buttons lead back to the page the note
    is on now, a page of `search`'s results when the card is in their message: a pin, or notes
    added in the app, move it. A note the search finds no more keeps the button's page."""
    if search is None:
        listed = await notes.list_for(ctx.session, ctx.user.id)
    else:
        listed = await notes.search(ctx.session, ctx.user.id, search)
    for position, note in enumerate(listed):
        if note.id == note_id:
            return card_view(note, position // PAGE_SIZE, ctx.t, results=search is not None)
    if search is None:
        return None
    try:
        note = await notes.get_view(ctx.session, ctx.user.id, note_id)
    except NotFound:
        return None
    _, page, _ = paginate(listed, page)
    return card_view(note, page, ctx.t, results=True)


async def _back(ctx: Ctx, query: CallbackQuery, page: int) -> View:
    """Where «↩️ К заметкам» leads from the button's message: the search's results while they are
    this message's, else the whole list. A search that finds nothing any more is over: the whole
    list from its start, and the message's buttons work as the list's again."""
    search = await _search_here(ctx, query)
    if search is not None:
        found = await notes.search(ctx.session, ctx.user.id, search)
        if found:
            return results_view(found, search, page, ctx.t)
        await _drop_search(ctx)
        page = 0
    return await _list(ctx, page)


async def _edit(bot: Bot, query: CallbackQuery, view: View) -> None:
    # Notes keep links written out, «тут (https://…)»: no preview card under the list or a card.
    await replies.edit(bot, query, *view, link_preview_options=NO_PREVIEW)


async def _gone(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """The note of the button was deleted, here or in the app: say so and show the notes from the
    start, the search's results in their message."""
    await replies.answer_quietly(query, ctx.t("already-deleted"))
    await _edit(bot, query, await _back(ctx, query, 0))


async def _show_card(
    query: CallbackQuery, ctx: Ctx, bot: Bot, note_id: int, page: int, answer: str | None = None
) -> None:
    """The note's card in the button's message, after what the button changed."""
    view = await _card(ctx, note_id, page, await _search_here(ctx, query))
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


async def on_found_page(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    """◀️ ▶️ of a search's results, and «↩️ К заметкам» of a card shown in their message; any
    other message, or one whose search was dropped, turns to the page of the list."""
    await query.answer()
    await _edit(bot, query, await _back(ctx, query, callback_data.page))


async def on_reset(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """«✖️ Сбросить поиск»: the whole list in place of the results. Only this message's search is
    dropped: a later one, with its results in another message, stays."""
    await query.answer()
    if await _search_here(ctx, query) is not None:
        await _drop_search(ctx)
    await _edit(bot, query, await _list(ctx, 0))


async def on_open(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    # "fopen", a note of a search's results, opens the same card: what leads back to the results
    # is the message the card is in, so «↩️ Назад» of the delete question keeps it too.
    await _show_card(query, ctx, bot, callback_data.id, callback_data.page)


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
    # An item's button carries no page: a note the search finds no more leads to its first.
    await _show_card(query, ctx, bot, callback_data.note, 0, answer)


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
        await replies.answer_quietly(
            query, ctx.t("pinned-limit", limit=LIMITS.pinned_notes), show_alert=True
        )
        return
    await _show_card(query, ctx, bot, callback_data.id, callback_data.page)


async def on_clear(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        await notes.clear_done(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    await _show_card(query, ctx, bot, callback_data.id, callback_data.page)


async def on_delete_ask(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        note = await notes.get_view(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    await replies.answer_quietly(query)
    await _edit(bot, query, confirm_view(note, callback_data.page, ctx.t))


async def on_delete(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    if not await notes.delete(ctx.session, ctx.user.id, callback_data.id):
        await _gone(query, ctx, bot)
        return
    await replies.answer_quietly(query, ctx.t("deleted"))
    # Where «↩️ К заметкам» led: the note's page, or the last page left when it was alone there;
    # the whole list once a search finds nothing more.
    await _edit(bot, query, await _back(ctx, query, callback_data.page))


async def _ask(
    query: CallbackQuery,
    ctx: Ctx,
    bot: Bot,
    state: State,
    question: str,
    data: dict[str, str | int],
) -> None:
    """Start a dialog with its question and «❌ Отмена». Its data replaces what was kept: a
    search's, too."""
    await query.answer()
    await ctx.state.set_state(state)
    await ctx.state.set_data(data)
    await replies.send(bot, query, question, cancel_menu(ctx.t))


async def _at_limit(query: CallbackQuery, ctx: Ctx) -> bool:
    """At the limit of notes a new one is refused before its dialog starts."""
    if await notes.count(ctx.session, ctx.user.id) < LIMITS.notes:
        return False
    await query.answer(ctx.t("notes-limit", limit=LIMITS.notes), show_alert=True)
    return True


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if not await _at_limit(query, ctx):
        ask = ctx.t("note-ask", limit=LIMITS.note_length)
        await _ask(query, ctx, bot, NoteForm.text, ask, {"hint": "hint-note"})


async def on_checklist(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if not await _at_limit(query, ctx):
        await _ask(query, ctx, bot, NoteForm.checklist, ctx.t("list-ask"), {"hint": "hint-list"})


async def on_find(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await _ask(query, ctx, bot, NoteForm.search, ctx.t("search-ask"), {"hint": "hint-search"})


async def on_edit(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        note = await notes.get_view(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    ask = ctx.t("note-edit-ask", limit=LIMITS.note_length)
    await _ask(query, ctx, bot, NoteForm.edit, ask, {"hint": "hint-note-edit", "note_id": note.id})


async def on_items(query: CallbackQuery, callback_data: NoteCb, ctx: Ctx, bot: Bot) -> None:
    try:
        note = await notes.get_view(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:
        await _gone(query, ctx, bot)
        return
    if note.total >= LIMITS.note_items:  # an old card's button: the note filled up since
        await query.answer(ctx.t("items-full", limit=LIMITS.note_items), show_alert=True)
        return
    ask = ctx.t("items-ask", limit=LIMITS.note_items)
    await _ask(query, ctx, bot, NoteForm.items, ask, {"hint": "hint-items", "note_id": note.id})


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


async def _dialog_note(ctx: Ctx) -> int:
    return int((await ctx.state.get_data()).get("note_id", 0))


async def _end(message: Message, ctx: Ctx, text: str, note_id: int | None = None) -> None:
    """Close a dialog: `text` with the main menu, then the note's card as a message of its own,
    since one message cannot carry both the menu and the card's buttons."""
    await ctx.state.clear()
    await message.answer(text, reply_markup=main_menu(ctx.t))
    view = await _card(ctx, note_id) if note_id is not None else None
    if view is not None:
        await message.answer(view[0], reply_markup=view[1], link_preview_options=NO_PREVIEW)


async def save_edit(message: Message, ctx: Ctx) -> None:
    """The note's new text, its hidden links written out as in a new note; its items stay."""
    note_id = await _dialog_note(ctx)
    text = notes.expand_links(message.text or "", message.entities)
    try:
        await notes.update_text(ctx.session, ctx.user.id, note_id, text)
    except NotFound:
        await _end(message, ctx, ctx.t("already-deleted"))
        return
    except InvalidInput:
        await message.answer(ctx.t("note-bad-text", limit=LIMITS.note_length))
        return
    await _end(message, ctx, ctx.t("note-updated"), note_id)


async def save_items(message: Message, ctx: Ctx) -> None:
    """New items for the note, a line each without its list marker: all of them, or none and
    what to change. A message of markers alone has no item and gets the hint."""
    note_id = await _dialog_note(ctx)
    items = notes.parse_item_lines(notes.expand_links(message.text or "", message.entities))
    refusal = _too_long(items, ctx.t) if items else ctx.t("hint-items")
    if refusal is not None:
        # It may quote an item that starts with an address: no preview card under it.
        await message.answer(refusal, link_preview_options=NO_PREVIEW)
        return
    try:
        added = await notes.add_items(ctx.session, ctx.user.id, note_id, items)
    except NotFound:
        await _end(message, ctx, ctx.t("already-deleted"))
        return
    except LimitReached:
        await _no_room(message, ctx, note_id)
        return
    await _end(message, ctx, ctx.t("items-added", count=len(added)), note_id)


async def _no_room(message: Message, ctx: Ctx, note_id: int) -> None:
    """More items than the note has room for: how many still fit, and the dialog waits; or, when
    the note filled up in the app while the question was open, the dialog ends with its card."""
    try:
        room = LIMITS.note_items - (await notes.get_view(ctx.session, ctx.user.id, note_id)).total
    except NotFound:
        await _end(message, ctx, ctx.t("already-deleted"))
        return
    if room > 0:
        await message.answer(ctx.t("items-room", count=room))
        return
    await _end(message, ctx, ctx.t("items-full", limit=LIMITS.note_items), note_id)


async def save_checklist(message: Message, ctx: Ctx) -> None:
    """A new checklist: the title from the first line, the items from the lines after it, hidden
    links written out in both."""
    title, items = split_list(notes.expand_links(message.text or "", message.entities))
    refusal = _list_refusal(title, items, ctx.t)
    if refusal is not None:
        await message.answer(refusal, link_preview_options=NO_PREVIEW)  # as in save_items
        return
    try:
        note = await notes.create(ctx.session, ctx.user.id, title, items, now=clock())
    except LimitReached:  # the last free place taken in the app while the question was open
        await _end(message, ctx, ctx.t("notes-limit", limit=LIMITS.notes))
        return
    await _end(message, ctx, ctx.t("list-saved"), note.id)


async def got_search(message: Message, ctx: Ctx) -> None:
    """The notes holding every word. Nothing found: the dialog waits for other words. Found: the
    dialog ends, and the results come in a message of their own, whose buttons apply the
    search."""
    try:
        found = await notes.search(ctx.session, ctx.user.id, message.text or "")
    except InvalidInput:
        await message.answer(ctx.t("search-bad", limit=LIMITS.search_length))
        return
    search = " ".join((message.text or "").split())
    if not found:
        # The words are quoted, «github.com» too: no preview card under the answer.
        await message.answer(ctx.t("search-empty", query=search), link_preview_options=NO_PREVIEW)
        return
    # No dialog any more, but its data stays: the search lives on with its results.
    await ctx.state.set_state(None)
    await message.answer(ctx.t("search-found", count=len(found)), reply_markup=main_menu(ctx.t))
    text, markup = results_view(found, search, 0, ctx.t)
    sent = await message.answer(text, reply_markup=markup, link_preview_options=NO_PREVIEW)
    # The id of the results, not of «🔍 Нашлось»: only the results' buttons apply the search.
    await ctx.state.update_data({QUERY: search, QUERY_MESSAGE: sent.message_id})


def create_router() -> Router:
    router = Router(name="notes")
    for actions, handler in (
        (("page",), on_page),
        (("fpage",), on_found_page),
        (("reset",), on_reset),
        (("open", "fopen"), on_open),
        (("pin", "unpin"), on_pin),
        (("clear",), on_clear),
        (("delask", "del"), on_delete_ask),
        (("delyes",), on_delete),
        (("add",), on_add),
        (("checklist",), on_checklist),
        (("find",), on_find),
        (("edit",), on_edit),
        (("items",), on_items),
    ):
        router.callback_query.register(handler, NoteCb.filter(F.action.in_(actions)))
    router.callback_query.register(on_item, NoteItemCb.filter())
    router.message.register(save_note, NoteForm.text, F.text)
    router.message.register(save_edit, NoteForm.edit, F.text)
    router.message.register(save_items, NoteForm.items, F.text)
    router.message.register(save_checklist, NoteForm.checklist, F.text)
    router.message.register(got_search, NoteForm.search, F.text)
    return router
