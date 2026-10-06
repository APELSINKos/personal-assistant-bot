"""Last resort: non-text input inside a dialog, anything unknown outside it, stale buttons.

Words the bot did not understand outside a dialog may be a note: the answer to them offers
«📝 В заметки», which saves the message it answered.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import KeepCb, NoteCb, main_menu
from assistant.bot.replies import NO_PREVIEW
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.services import notes
from assistant.core.services.notes import NoteView
from assistant.core.timeutil import utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
# A tap on «📝 В заметки» this soon after a note with the same words keeps that note instead of
# making another. A user's updates run one at a time, so a double tap's second update comes once
# the first is done, with the answer as it was, the button still under it.
KEEP_AGAIN = timedelta(seconds=60)


async def unknown(message: Message, ctx: Ctx) -> None:
    """«Не понял» with the main menu: for what cannot be a note, and after a dialog that is gone
    (orphan_state, reminders._no_dialog), whose «❌ Отмена» may still be on the screen."""
    text = f"{ctx.t('unknown')}\n{ctx.t('unknown-hint')}"
    await message.answer(text, reply_markup=main_menu(ctx.t))


def _note_text(message: Message) -> str | None:
    """What «📝 В заметки» keeps of a message: its text, or the caption of its photo or file,
    hidden links written out as in a note typed in the bot; None when it has neither."""
    if message.text:
        return notes.expand_links(message.text, message.entities)
    if message.caption:
        return notes.expand_links(message.caption, message.caption_entities)
    return None


async def not_understood(message: Message, ctx: Ctx) -> None:
    """Anything no section took, outside a dialog. Words a note can keep, while there is room
    for one, get «📝 В заметки» under the answer; a command («/x») never does."""
    text = _note_text(message)
    if (
        text is None
        or text.startswith("/")
        or not 1 <= len(text.strip()) <= LIMITS.note_length
        or await notes.count(ctx.session, ctx.user.id) >= LIMITS.notes
    ):
        await unknown(message, ctx)
        return
    keep = InlineKeyboardButton(text=ctx.t("button-keep"), callback_data=KeepCb().pack())
    # A reply, since the button saves the message it answers; sent even if that message is
    # deleted meanwhile. No main menu: a message has one keyboard, and the menu stays anyway.
    await message.answer(
        f"{ctx.t('unknown-keep')}\n{ctx.t('unknown-hint')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[keep]]),
        reply_parameters=ReplyParameters(
            message_id=message.message_id, allow_sending_without_reply=True
        ),
    )


async def _kept_just_now(ctx: Ctx, text: str) -> NoteView | None:
    """The newest of the user's notes with these words, when it is younger than KEEP_AGAIN."""
    same = [note for note in await notes.list_for(ctx.session, ctx.user.id) if note.text == text]
    newest = max(same, key=lambda note: note.id, default=None)
    if newest is None or clock() - newest.created_at >= KEEP_AGAIN:
        return None
    return newest


async def on_keep(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """«📝 В заметки»: the message the answer replies to becomes a note."""
    answer = query.message
    source = answer.reply_to_message if isinstance(answer, Message) else None
    text = None if source is None else _note_text(source)
    if text is None:
        # The user deleted the message or edited its caption away, or the answer is too old for
        # Telegram to show what it replies to.
        await query.answer(ctx.t("keep-gone"))
        await replies.drop_buttons(bot, query)
        return
    # Compared as a note keeps them: without the spaces around.
    note = await _kept_just_now(ctx, text.strip())
    if note is None:
        try:
            note = await notes.create(ctx.session, ctx.user.id, text, now=clock())
        except InvalidInput:  # the message was edited past the limit after the answer
            await query.answer(ctx.t("keep-too-long", limit=LIMITS.note_length), show_alert=True)
            await replies.drop_buttons(bot, query)
            return
        except LimitReached:  # the button stays: it saves once a note is deleted
            await query.answer(ctx.t("notes-limit", limit=LIMITS.notes), show_alert=True)
            return
    await replies.answer_quietly(query)
    opener = NoteCb(action="open", id=note.id).pack()
    button = InlineKeyboardButton(text=ctx.t("button-open-note"), callback_data=opener)
    markup = InlineKeyboardMarkup(inline_keyboard=[[button]])
    await replies.edit(bot, query, ctx.t("note-saved"), markup, link_preview_options=NO_PREVIEW)


async def need_text(message: Message, ctx: Ctx) -> None:
    hint_key = (await ctx.state.get_data()).get("hint")
    hint = ctx.t(hint_key) if hint_key else ""
    if hint == hint_key:
        # A stale hint key left by an old release (the translator echoes an unknown key
        # back unchanged): nothing sensible to show.
        hint = ""
    await message.answer(ctx.t("need-text", hint=hint))


async def orphan_state(message: Message, ctx: Ctx) -> None:
    # A state no router handles any more (e.g. after an update): start over.
    await ctx.state.clear()
    await unknown(message, ctx)


async def stale_button(query: CallbackQuery, ctx: Ctx) -> None:
    await query.answer(ctx.t("stale-button"))


def create_router() -> Router:
    router = Router(name="fallback")
    router.message.register(not_understood, StateFilter(None))
    router.message.register(need_text, ~F.text)
    router.message.register(orphan_state)
    router.callback_query.register(on_keep, KeepCb.filter())
    router.callback_query.register(stale_button)
    return router
