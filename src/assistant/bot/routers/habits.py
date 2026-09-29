"""🎯 Habits: statistics with a 9-day strip, marking today, adding and deleting."""

from __future__ import annotations

from datetime import date

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import HabitCb, cancel_menu, main_menu
from assistant.bot.sections import section
from assistant.bot.states import HabitForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.i18n import Translator, format_day
from assistant.core.services import habits
from assistant.core.services.habits import HabitStats
from assistant.core.timeutil import local_today

STRIP = {True: "🟩", False: "🟥", None: "⬜"}
MARK = {True: "✅", False: "❌", None: "⬜"}
NEXT_MARK: dict[bool | None, bool | None] = {None: True, True: False, False: None}
FIRE_FROM = 3  # a streak of this many days earns a 🔥


def _button(text: str, data: HabitCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def habits_view(items: list[HabitStats], t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    add = _button(t("button-add"), HabitCb(action="add"))
    if not items:
        return t("habits-empty"), InlineKeyboardMarkup(inline_keyboard=[[add]])
    lines = [t("habits-title", count=len(items), limit=LIMITS.habits)]
    for number, stats in enumerate(items, start=1):
        fire = " 🔥" if stats.streak >= FIRE_FROM else ""
        strip = "".join(STRIP[day] for day in stats.last_days)
        lines += [
            "",
            t(
                "habit-line",
                number=number,
                name=stats.habit.name,
                done=stats.done_days,
                total=stats.total_days,
                fire=fire,
            ),
            "    " + t("habit-days", strip=strip, count=stats.streak),
        ]
    lines += ["", t("habits-legend")]
    rows = [
        [_button(t("button-mark-today"), HabitCb(action="mark"))],
        [add, _button(t("button-delete"), HabitCb(action="delete"))],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def mark_view(
    items: list[HabitStats], day: date, t: Translator
) -> tuple[str, InlineKeyboardMarkup]:
    done = sum(1 for stats in items if stats.done_today)
    text = "\n".join(
        [
            t("habits-mark-title", date=format_day(day, t.lang)),
            t("habits-mark-help"),
            "",
            t("habits-mark-progress", done=done, total=len(items)),
        ]
    )
    rows = [
        [
            _button(
                f"{MARK[stats.done_today]} {stats.habit.name}",
                HabitCb(action="toggle", id=stats.habit.id),
            )
        ]
        for stats in items
    ]
    rows.append([_button(t("button-back"), HabitCb(action="list"))])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def delete_view(items: list[HabitStats], t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [_button(f"🗑 {stats.habit.name}", HabitCb(action="ask", id=stats.habit.id))]
        for stats in items
    ]
    rows.append([_button(t("button-back"), HabitCb(action="list"))])
    return t("habits-delete-title"), InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_view(stats: HabitStats, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [_button(t("button-confirm-delete"), HabitCb(action="del", id=stats.habit.id))],
        [_button(t("button-back"), HabitCb(action="list"))],
    ]
    return (
        t("habit-delete-confirm", name=stats.habit.name),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _items(ctx: Ctx) -> list[HabitStats]:
    return await habits.list_with_stats(ctx.session, ctx.user)


@section("habits")
async def show_habits(message: Message, ctx: Ctx) -> None:
    text, markup = habits_view(await _items(ctx), ctx.t)
    await message.answer(text, reply_markup=markup)


async def on_list(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *habits_view(await _items(ctx), ctx.t))


async def on_mark(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    items = await _items(ctx)
    if not items:
        await query.answer(ctx.t("habits-need-one"), show_alert=True)
        return
    await query.answer()
    today = local_today(ctx.user.timezone)
    await replies.edit(bot, query, *mark_view(items, today, ctx.t))


async def on_toggle(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    today = local_today(ctx.user.timezone)
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id)
        await habits.set_mark(
            ctx.session, ctx.user, stats.habit.id, today, NEXT_MARK[stats.done_today]
        )
    except NotFound:
        await query.answer(ctx.t("already-deleted"))
    except InvalidInput:
        # Today is outside the habit's days, e.g. the user moved west on the day it was
        # created: nothing to mark, the list below shows the current state.
        await query.answer(ctx.t("stale-button"))
    else:
        await replies.answer_quietly(query)
    items = await _items(ctx)
    if items:
        await replies.edit(bot, query, *mark_view(items, today, ctx.t))
    else:
        await replies.edit(bot, query, *habits_view(items, ctx.t))


async def on_delete_menu(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    items = await _items(ctx)
    view = delete_view(items, ctx.t) if items else habits_view(items, ctx.t)
    await replies.edit(bot, query, *view)


async def on_ask(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id)
    except NotFound:
        await query.answer(ctx.t("already-deleted"))
        await replies.edit(bot, query, *habits_view(await _items(ctx), ctx.t))
        return
    await query.answer()
    await replies.edit(bot, query, *confirm_view(stats, ctx.t))


async def on_delete(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    removed = await habits.delete(ctx.session, ctx.user.id, callback_data.id)
    await replies.answer_quietly(query, ctx.t("deleted" if removed else "already-deleted"))
    await replies.edit(bot, query, *habits_view(await _items(ctx), ctx.t))


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if len(await _items(ctx)) >= LIMITS.habits:
        await query.answer(ctx.t("habits-limit", limit=LIMITS.habits), show_alert=True)
        return
    await query.answer()
    await ctx.state.set_state(HabitForm.name)
    await ctx.state.set_data({"hint": "hint-habit"})
    await replies.send(
        bot, query, ctx.t("habit-ask", limit=LIMITS.habit_length), cancel_menu(ctx.t)
    )


async def save_habit(message: Message, ctx: Ctx) -> None:
    try:
        habit = await habits.create(ctx.session, ctx.user, message.text or "")
    except InvalidInput as error:
        key = "habit-duplicate" if error.params.get("reason") == "duplicate" else "habit-bad-name"
        await message.answer(ctx.t(key, limit=LIMITS.habit_length))
        return
    except LimitReached:
        await ctx.state.clear()
        await message.answer(
            ctx.t("habits-limit", limit=LIMITS.habits), reply_markup=main_menu(ctx.t)
        )
        return
    await ctx.state.clear()
    await message.answer(ctx.t("habit-added", name=habit.name), reply_markup=main_menu(ctx.t))


def create_router() -> Router:
    router = Router(name="habits")
    for action, handler in (
        ("list", on_list),
        ("mark", on_mark),
        ("toggle", on_toggle),
        ("delete", on_delete_menu),
        ("ask", on_ask),
        ("del", on_delete),
        ("add", on_add),
    ):
        router.callback_query.register(handler, HabitCb.filter(F.action == action))
    router.message.register(save_habit, HabitForm.name, F.text)
    return router
