"""⏰ Reminders: a phrase anywhere → a confirmation card, the list with repeats, deletion."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import (
    PAGE_SIZE,
    FireCb,
    ReminderCb,
    cancel_menu,
    card_markup,
    main_menu,
    page_buttons,
    paginate,
    preview,
    time_choices,
)
from assistant.bot.routers import fallback
from assistant.bot.sections import section
from assistant.bot.states import ReminderForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.i18n import Translator
from assistant.core.models import Reminder, ReminderStatus, Repeat, User
from assistant.core.services import phrases, reminders
from assistant.core.services.phrases import Parsed
from assistant.core.services.recurrence import describe
from assistant.core.timeutil import parse_hhmm, to_local, utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
Send = Callable[[str, Any], Awaitable[Any]]
# A card (or a time prompt) older than this is treated as gone, whether or not it was pressed.
CARD_TTL = timedelta(hours=24)


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
    tail: list[str] = []
    if pages > 1:
        tail = ["", t("page", current=page + 1, total=pages)]
        rows.append(
            page_buttons(t, page, pages, lambda p: ReminderCb(action="page", page=p).pack())
        )
    rows.append(add)
    return texts.fit(lines, tail), InlineKeyboardMarkup(inline_keyboard=rows)


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
    card = secrets.randbelow(10**9) + 1
    await ctx.state.set_state(ReminderForm.time)
    await ctx.state.set_data(
        {
            "parsed": phrases.dump(parsed),
            "at": local_now.isoformat(),
            "tz": ctx.user.timezone,
            "card": card,
            "hint": "hint-reminder-time",
        }
    )
    await send(ctx.t("reminder-ask-time"), time_choices(ctx.t, card))


async def _offer(send: Send, ctx: Ctx, parsed: Parsed, local_now: datetime) -> None:
    """Show the card, or ask for what the phrase is missing."""
    if not parsed.text.strip():
        await ctx.state.set_state(ReminderForm.text)
        await ctx.state.set_data({"hint": "hint-reminder-phrase"})
        await send(ctx.t("reminder-need-text"), None)
        return
    try:
        reminders.clean_text(parsed.text)
    except InvalidInput:
        await ctx.state.set_state(ReminderForm.text)
        await ctx.state.set_data({"hint": "hint-reminder-phrase"})
        await send(ctx.t("reminder-long-text", limit=LIMITS.reminder_length), None)
        return
    if parsed.needs_time:
        await _ask_time(send, ctx, parsed, local_now)
        return
    when = parsed.when(local_now)
    # «через …» is always ahead (✅ checks the real clock), and naive wall times compare
    # wrongly inside the hour that repeats when the clocks go back.
    if when is not None and parsed.delta is None and when <= local_now.replace(tzinfo=None):
        await send(ctx.t("reminder-past"), None)
        await _ask_time(send, ctx, parsed, local_now)
        return
    card = secrets.randbelow(10**9) + 1
    await ctx.state.set_state(ReminderForm.confirm)
    await ctx.state.set_data(
        {
            "parsed": phrases.dump(parsed),
            "at": local_now.isoformat(),
            "tz": ctx.user.timezone,
            "card": card,
            "hint": "reminder-use-card",
        }
    )
    await send(texts.card_text(parsed, local_now, ctx.t), card_markup(ctx.t, card))


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


async def _no_dialog(message: Message, ctx: Ctx, local_now: datetime) -> None:
    """A prompt or card that is gone: handle the message as if no dialog were open."""
    await ctx.state.clear()
    parsed = phrases.parse(message.text or "", local_now)
    if parsed is not None:
        await _offer(_answer(message), ctx, parsed, local_now)
    else:
        await fallback.unknown(message, ctx)


async def got_reply_while_confirm(message: Message, ctx: Ctx) -> None:
    """A card is open: a new phrase replaces it; anything else just points back to it."""
    local_now = _local_now(ctx)
    draft = await _draft(ctx)
    if draft is None or _expired(draft):
        await _no_dialog(message, ctx, local_now)
        return
    parsed = phrases.parse(message.text or "", local_now)
    if parsed is not None:
        await _offer(_answer(message), ctx, parsed, local_now)
        return
    await message.answer(ctx.t("reminder-use-card"))


@dataclass
class _Draft:
    """A phrase waiting for a time, or a confirmation card: what it says and whose it is."""

    parsed: Parsed
    at: datetime
    card: int
    tz: str | None  # the zone it was drawn in; a draft kept before 2.6.1 has none


async def _draft(ctx: Ctx) -> _Draft | None:
    data = await ctx.state.get_data()
    raw, at, card = data.get("parsed"), data.get("at"), data.get("card")
    if not isinstance(raw, dict) or not isinstance(at, str) or not isinstance(card, int):
        return None
    tz = data.get("tz")
    return _Draft(
        parsed=phrases.load(raw),
        at=datetime.fromisoformat(at),
        card=card,
        tz=tz if isinstance(tz, str) else None,
    )


def _expired(draft: _Draft) -> bool:
    return clock() - draft.at > CARD_TTL


def _is_new_phrase(answer: Parsed) -> bool:
    """A reply at the time prompt with its own text and its own day or repeat is a phrase of
    its own, not an answer: «завтра в 9 купить молоко». Bare answers («18:30», «завтра в 10»,
    «в 18 обязательно») complete the waiting draft instead."""
    anchored = (
        answer.day is not None
        or answer.weekday is not None
        or answer.repeat is not Repeat.NONE
        or answer.delta is not None
        or answer.delta_days is not None
    )
    return anchored and bool(answer.text.strip())


async def _verified(
    query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot
) -> _Draft | None:
    """The draft behind a pressed card button, if the button still belongs to it.

    Three cases all answer the button with `already-deleted` and drop its keyboard, but
    differ in what they do to the state:
    - no draft at all (there may be no reminder dialog here — e.g. an unrelated FSM dialog
      is in progress under a stale reminder-card button): the state is left untouched;
    - a draft that outlived `CARD_TTL`: nothing usable is left, so the state is cleared;
    - a draft whose `card` does not match the pressed button's `id` (a newer draft replaced
      it): the state is left untouched, since that newer draft may still be alive under it.
    """
    draft = await _draft(ctx)
    expired = draft is not None and _expired(draft)
    if draft is None or expired or draft.card != callback_data.id:
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        await replies.drop_buttons(bot, query)
        if expired:
            await ctx.state.clear()
        return None
    return draft


async def got_time(message: Message, ctx: Ctx) -> None:
    draft = await _draft(ctx)
    local_now = _local_now(ctx)
    if draft is None or _expired(draft):
        await _no_dialog(message, ctx, local_now)
        return
    text = (message.text or "").strip()
    answer = phrases.parse(text, local_now)
    if answer is not None and _is_new_phrase(answer):
        await _offer(_answer(message), ctx, answer, local_now)
        return
    answer = answer or phrases.parse(f"в {text}", local_now)
    if answer is not None:
        merged = phrases.merge(draft.parsed, answer)
        if not merged.needs_time:
            await _offer(_answer(message), ctx, merged, local_now)
            return
    await _ask_time(_answer(message), ctx, draft.parsed, local_now)


async def on_time_choice(
    query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot
) -> None:
    hhmm = parse_hhmm(callback_data.value)
    if hhmm is None:  # not one of our buttons: nothing changes
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        return
    draft = await _verified(query, callback_data, ctx, bot)
    if draft is None:
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    parsed = draft.parsed.with_time(hhmm)
    await _offer(_send_to(bot, query), ctx, parsed, _local_now(ctx))


async def on_create(query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot) -> None:
    draft = await _verified(query, callback_data, ctx, bot)
    if draft is None:
        return
    # Read, then clear right away: it narrows a double tap on ✅ to a single creation.
    # A failure path below sets the state it needs again.
    await ctx.state.clear()
    parsed, card_now = draft.parsed, draft.at
    send = _send_to(bot, query)
    if draft.tz is not None and draft.tz != ctx.user.timezone:
        # The home city changed under the card (in the app), so its time meant the old zone:
        # the card comes again in the new one, and this tap saves nothing.
        await replies.answer_quietly(query)
        await replies.drop_buttons(bot, query)
        await _offer(send, ctx, parsed, _local_now(ctx))
        return
    try:
        if parsed.repeat is not Repeat.NONE:
            # The first firing is counted from the press, never from when the card was shown.
            reminder = await reminders.create_from(ctx.session, ctx.user, parsed, clock())
        else:
            # The card's own "now" for the wall time: «через 20 минут» means what the card
            # showed. The draft keeps only its offset: back in the zone, a change of clocks
            # inside the span counts. The past check itself still runs against the real clock.
            when = parsed.when(to_local(card_now, ctx.user.timezone))
            if when is None:
                raise InvalidInput(field="when", reason="needs_time")
            reminder = await reminders.create(ctx.session, ctx.user, parsed.text, when, clock())
    except LimitReached:
        await replies.answer_quietly(query)
        await replies.drop_buttons(bot, query)
        await send(ctx.t("reminders-limit", limit=LIMITS.reminders), main_menu(ctx.t))
        return
    except InvalidInput as error:
        await replies.answer_quietly(query)
        await replies.drop_buttons(bot, query)
        if error.params.get("field") == "text":
            await send(ctx.t("reminder-long-text", limit=LIMITS.reminder_length), None)
            await ctx.state.set_state(ReminderForm.text)
            await ctx.state.set_data({"hint": "hint-reminder-phrase"})
            return
        if error.params.get("reason") == "past":
            await send(ctx.t("reminder-past"), None)
        await _ask_time(send, ctx, parsed, _local_now(ctx))
        return
    await replies.answer_quietly(query)
    await replies.drop_buttons(bot, query)
    saved = texts.saved_text(reminder, ctx.user.timezone, _local_now(ctx), ctx.t)
    await send(saved, main_menu(ctx.t))


async def on_retime(query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot) -> None:
    draft = await _verified(query, callback_data, ctx, bot)
    if draft is None:
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    await _ask_time(_send_to(bot, query), ctx, draft.parsed, _local_now(ctx))


async def on_card_cancel(
    query: CallbackQuery, callback_data: ReminderCb, ctx: Ctx, bot: Bot
) -> None:
    draft = await _verified(query, callback_data, ctx, bot)
    if draft is None:
        return
    await ctx.state.clear()
    await replies.answer_quietly(query)
    await replies.drop_buttons(bot, query)
    await replies.send(bot, query, ctx.t("cancelled"), main_menu(ctx.t))


FIRED_TTL = timedelta(days=7)


def _moment_label(moment: datetime, ctx: Ctx, now: datetime) -> str:
    tz = ctx.user.timezone
    if to_local(moment, tz).date() == to_local(now, tz).date():
        return texts.local_time(moment, tz)
    return texts.short_moment(moment, tz, ctx.lang, now)


async def on_fired(query: CallbackQuery, callback_data: FireCb, ctx: Ctx, bot: Bot) -> None:
    """«+10 мин / +1 ч / Завтра / ✓ Готово» under a delivered reminder."""
    now = clock()
    fired_at = datetime.fromtimestamp(callback_data.at * 60, UTC)
    shown_text = getattr(query.message, "text", None) or ""

    async def gone() -> None:
        await replies.answer_quietly(query, ctx.t("already-deleted"))
        await replies.drop_buttons(bot, query)

    if now - fired_at > FIRED_TTL:
        await gone()
        return
    if callback_data.action == "done":
        if not await reminders.done(ctx.session, ctx.user.id, callback_data.id):
            await gone()
            return
        result = ctx.t("fired-done")
    elif callback_data.action in reminders.SNOOZE_KINDS:
        until = reminders.snooze_until(callback_data.action, fired_at, ctx.user.timezone, now)
        try:
            await reminders.snooze(ctx.session, ctx.user, callback_data.id, until, now)
        except NotFound:
            await gone()
            return
        except LimitReached:
            await query.answer(ctx.t("reminders-limit", limit=LIMITS.reminders), show_alert=True)
            return
        result = ctx.t("fired-snoozed", when=_moment_label(until, ctx, now))
    else:
        await gone()
        return
    if not shown_text:
        # An InaccessibleMessage (too old for Bot API to return its text) must not turn
        # the edit into a bare confirmation: fall back to the reminder's own fire text.
        source = await reminders.get_owned(ctx.session, ctx.user.id, callback_data.id)
        if source is None:
            await gone()
            return
        shown_text = ctx.t("reminder-fire", text=source.text)
    await replies.edit(bot, query, f"{shown_text}\n\n{result}", None)
    await replies.answer_quietly(query)


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
    router.message.register(got_reply_while_confirm, ReminderForm.confirm, F.text)
    router.message.register(got_time, ReminderForm.time, F.text)
    router.message.register(phrase_anywhere, StateFilter(None), F.text.func(looks_like_reminder))
    router.callback_query.register(on_fired, FireCb.filter())
    return router
