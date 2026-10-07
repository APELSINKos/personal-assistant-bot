"""🎯 Habits: statistics with a 9-day strip, marking today, adding and deleting, and a habit's
own card — its year as a picture, the last days, the weekly goal, emoji and colour, its name."""

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

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import HabitCb, cancel_menu, main_menu
from assistant.bot.sections import section
from assistant.bot.states import HabitForm
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.habit_style import COLORS, DAILY, EMOJI
from assistant.core.i18n import Translator, format_day, weekday_short
from assistant.core.services import cards, habits
from assistant.core.services.habits import HabitStats
from assistant.core.timeutil import local_today, utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
STRIP = {True: "🟩", False: "🟥", None: "⬜"}
MARK = {True: "✅", False: "❌", None: "⬜"}
NEXT_MARK: dict[bool | None, bool | None] = {None: True, True: False, False: None}
FIRE_FROM = 3  # a streak of this many days (or weeks) earns a 🔥
DAYS_BACK = 7  # «📅 Прошлые дни» offers today and the six days before it
ROW = 4  # buttons in a row of days and emoji


def _button(text: str, data: HabitCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def _rows(buttons: list[InlineKeyboardButton], width: int) -> list[list[InlineKeyboardButton]]:
    return [buttons[start : start + width] for start in range(0, len(buttons), width)]


def habits_view(items: list[HabitStats], t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    add = _button(t("button-add"), HabitCb(action="add"))
    if not items:
        return t("habits-empty"), InlineKeyboardMarkup(inline_keyboard=[[add]])
    lines = [t("habits-title", count=len(items), limit=LIMITS.habits)]
    for number, stats in enumerate(items, start=1):
        habit = stats.habit
        fire = " 🔥" if stats.streak >= FIRE_FROM else ""
        strip = "".join(STRIP[day] for day in stats.last_days)
        if stats.unit == "days":
            line = t(
                "habit-line",
                number=number,
                emoji=habit.emoji,
                name=habit.name,
                done=stats.done_days,
                total=stats.total_days,
                fire=fire,
            )
            streak = t("habit-days", strip=strip, count=stats.streak)
        else:  # a weekly goal: this week's progress and a streak of weeks
            line = t(
                "habit-line-weekly",
                number=number,
                emoji=habit.emoji,
                name=habit.name,
                done=stats.week_done,
                goal=stats.week_goal,
                fire=fire,
            )
            streak = t("habit-weeks", strip=strip, count=stats.streak)
        lines += ["", line, "    " + streak]
    opens = [
        _button(
            f"{stats.habit.emoji} {stats.habit.name}", HabitCb(action="open", id=stats.habit.id)
        )
        for stats in items
    ]
    rows = [
        *_rows(opens, 2),
        [_button(t("button-mark-today"), HabitCb(action="mark"))],
        [add, _button(t("button-delete"), HabitCb(action="delete"))],
    ]
    return texts.fit(lines, ["", t("habits-legend")]), InlineKeyboardMarkup(inline_keyboard=rows)


def goal_text(weekly_goal: int, t: Translator) -> str:
    if weekly_goal == DAILY:
        return t("card-goal-daily")
    return t("card-goal-weekly", count=weekly_goal)


def habit_view(stats: HabitStats, today: date, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    """A habit's own card: its goal, streak, record, past year and this week."""
    habit = stats.habit
    text = "\n".join(
        [
            f"{habit.emoji} {habit.name}",
            cards.subtitle(habit.weekly_goal, habit.created_on, today, t),
            "",
            t(f"habit-card-streak-{stats.unit}", count=stats.streak),
            t(f"habit-card-record-{stats.unit}", count=stats.record),
            t("habit-card-year", percent=stats.percent),
            t("habit-card-week", done=stats.week_done, goal=stats.week_goal),
        ]
    )
    own = habit.id
    rows = [
        [
            _button(t("button-habit-map"), HabitCb(action="map", id=own)),
            _button(t("button-habit-days"), HabitCb(action="days", id=own)),
        ],
        [
            _button(t("button-habit-goal"), HabitCb(action="goal", id=own)),
            _button(t("button-habit-style"), HabitCb(action="style", id=own)),
        ],
        [
            _button(t("button-habit-rename"), HabitCb(action="rename", id=own)),
            _button(t("button-delete"), HabitCb(action="ask", id=own)),
        ],
        [_button(t("button-to-habits"), HabitCb(action="list"))],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def recent_days(stats: HabitStats, today: date) -> list[tuple[date, bool | None]]:
    """The last DAYS_BACK days, oldest first, never before the habit began, with their marks."""
    first = max(stats.habit.created_on, today - timedelta(days=DAYS_BACK - 1))
    return [
        (today - timedelta(days=back), stats.last_days[-1 - back])
        for back in range((today - first).days, -1, -1)
    ]


def days_view(stats: HabitStats, today: date, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    habit = stats.habit
    text = "\n".join(
        [t("habit-days-title", emoji=habit.emoji, name=habit.name), t("habit-days-help")]
    )
    days = [
        _button(
            f"{weekday_short(day.weekday(), t.lang)} {day.day} {MARK[mark]}",
            HabitCb(action="day", id=habit.id, value=day.isoformat()),
        )
        for day, mark in recent_days(stats, today)
    ]
    rows = [*_rows(days, ROW), [_button(t("button-back"), HabitCb(action="open", id=habit.id))]]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def goal_view(stats: HabitStats, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    habit = stats.habit

    def choice(goal: int) -> InlineKeyboardButton:
        mark = "• " if goal == habit.weekly_goal else ""
        return _button(
            mark + goal_text(goal, t), HabitCb(action="setgoal", id=habit.id, value=str(goal))
        )

    rows = [
        [choice(DAILY)],
        [choice(6), choice(5), choice(4)],
        [choice(3), choice(2), choice(1)],
        [_button(t("button-back"), HabitCb(action="open", id=habit.id))],
    ]
    return t("habit-goal-ask", name=habit.name), InlineKeyboardMarkup(inline_keyboard=rows)


def emoji_view(stats: HabitStats, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    habit = stats.habit
    choices = [
        _button(emoji, HabitCb(action="emoji", id=habit.id, value=str(index)))
        for index, emoji in enumerate(EMOJI)
    ]
    rows = [*_rows(choices, ROW), [_button(t("button-back"), HabitCb(action="open", id=habit.id))]]
    return t("habit-emoji-ask", name=habit.name), InlineKeyboardMarkup(inline_keyboard=rows)


def color_view(stats: HabitStats, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    habit = stats.habit
    choices = [
        _button(colour.circle, HabitCb(action="color", id=habit.id, value=key))
        for key, colour in COLORS.items()
    ]
    rows = [*_rows(choices, ROW), [_button(t("button-back"), HabitCb(action="open", id=habit.id))]]
    return t("habit-color-ask"), InlineKeyboardMarkup(inline_keyboard=rows)


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


def _number(value: str, low: int, high: int) -> int | None:
    """A small number from a button, or None for anything a real button never carries."""
    if not (value.isascii() and value.isdigit() and len(value) <= 2):
        return None
    number = int(value)
    return number if low <= number <= high and str(number) == value else None


async def _items(ctx: Ctx, now: datetime) -> list[HabitStats]:
    return await habits.list_with_stats(ctx.session, ctx.user, now=now)


async def _gone(query: CallbackQuery, ctx: Ctx, bot: Bot, now: datetime) -> None:
    """The habit of the button no longer exists: say so and show the list."""
    await query.answer(ctx.t("already-deleted"))
    await replies.edit(bot, query, *habits_view(await _items(ctx, now), ctx.t))


@section("habits")
async def show_habits(message: Message, ctx: Ctx) -> None:
    text, markup = habits_view(await _items(ctx, clock()), ctx.t)
    await message.answer(text, reply_markup=markup)


async def on_list(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *habits_view(await _items(ctx, clock()), ctx.t))


async def on_open(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await replies.edit(bot, query, *habit_view(stats, local_today(ctx.user.timezone, now), ctx.t))


async def on_map(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    """The habit's year as a picture: the same card the Mini App shares, to forward anywhere."""
    now = clock()
    try:
        detail = await habits.detail(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    await query.answer()
    me = await bot.me()
    card = cards.card_for(detail, local_today(ctx.user.timezone, now), me.username or "")
    image = await cards.draw_card(card, ctx.t)
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="habit.jpg"),
        caption=cards.caption(card, ctx.t),
    )


async def on_days(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await replies.edit(bot, query, *days_view(stats, local_today(ctx.user.timezone, now), ctx.t))


async def on_day(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    today = local_today(ctx.user.timezone, now)
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    try:
        day = date.fromisoformat(callback_data.value)
    except ValueError:
        day = None
    if day is None or not today - timedelta(days=DAYS_BACK - 1) <= day <= today:
        await query.answer(ctx.t("stale-button"))  # forged, or from a days view of another day
        return
    current = stats.last_days[-1 - (today - day).days]
    try:
        stats = await habits.set_mark(
            ctx.session, ctx.user, stats.habit.id, day, NEXT_MARK[current], now=now
        )
    except InvalidInput:  # a day before the habit began
        await query.answer(ctx.t("stale-button"))
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *days_view(stats, today, ctx.t))


async def on_goal(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await replies.edit(bot, query, *goal_view(stats, ctx.t))


async def on_set_goal(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    goal = _number(callback_data.value, 1, DAILY)
    if goal is None:
        await query.answer(ctx.t("stale-button"))
        return
    now = clock()
    try:
        stats = await habits.update(
            ctx.session, ctx.user, callback_data.id, now=now, weekly_goal=goal
        )
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *habit_view(stats, local_today(ctx.user.timezone, now), ctx.t))


async def on_style(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await replies.edit(bot, query, *emoji_view(stats, ctx.t))


async def on_emoji(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    index = _number(callback_data.value, 0, len(EMOJI) - 1)
    if index is None:
        await query.answer(ctx.t("stale-button"))
        return
    now = clock()
    try:
        stats = await habits.update(
            ctx.session, ctx.user, callback_data.id, now=now, emoji=EMOJI[index]
        )
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *color_view(stats, ctx.t))


async def on_color(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    if callback_data.value not in COLORS:
        await query.answer(ctx.t("stale-button"))
        return
    now = clock()
    try:
        stats = await habits.update(
            ctx.session, ctx.user, callback_data.id, now=now, color=callback_data.value
        )
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *habit_view(stats, local_today(ctx.user.timezone, now), ctx.t))


async def on_rename(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await ctx.state.set_state(HabitForm.rename)
    await ctx.state.set_data({"hint": "hint-habit", "habit_id": stats.habit.id})
    ask = ctx.t("habit-rename-ask", name=stats.habit.name, limit=LIMITS.habit_length)
    await replies.send(bot, query, ask, cancel_menu(ctx.t))


async def save_rename(message: Message, ctx: Ctx) -> None:
    data = await ctx.state.get_data()
    try:
        stats = await habits.update(
            ctx.session, ctx.user, int(data["habit_id"]), now=clock(), name=message.text or ""
        )
    except NotFound:
        await ctx.state.clear()
        await message.answer(ctx.t("already-deleted"), reply_markup=main_menu(ctx.t))
        return
    except InvalidInput as error:
        key = "habit-duplicate" if error.params.get("reason") == "duplicate" else "habit-bad-name"
        await message.answer(ctx.t(key, limit=LIMITS.habit_length))
        return
    await ctx.state.clear()
    await message.answer(
        ctx.t("habit-renamed", name=stats.habit.name), reply_markup=main_menu(ctx.t)
    )


async def on_mark(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    items = await _items(ctx, now)
    if not items:
        await query.answer(ctx.t("habits-need-one"), show_alert=True)
        return
    await query.answer()
    today = local_today(ctx.user.timezone, now)
    await replies.edit(bot, query, *mark_view(items, today, ctx.t))


async def on_toggle(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    today = local_today(ctx.user.timezone, now)
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
        await habits.set_mark(
            ctx.session, ctx.user, stats.habit.id, today, NEXT_MARK[stats.done_today], now=now
        )
    except NotFound:
        await query.answer(ctx.t("already-deleted"))
    except InvalidInput:
        # Today is outside the habit's days, e.g. the user moved west on the day it was
        # created: nothing to mark, the list below shows the current state.
        await query.answer(ctx.t("stale-button"))
    else:
        await replies.answer_quietly(query)
    items = await _items(ctx, now)
    if items:
        await replies.edit(bot, query, *mark_view(items, today, ctx.t))
    else:
        await replies.edit(bot, query, *habits_view(items, ctx.t))


async def on_delete_menu(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    items = await _items(ctx, clock())
    view = delete_view(items, ctx.t) if items else habits_view(items, ctx.t)
    await replies.edit(bot, query, *view)


async def on_ask(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    now = clock()
    try:
        stats = await habits.stats_for(ctx.session, ctx.user, callback_data.id, now=now)
    except NotFound:
        await _gone(query, ctx, bot, now)
        return
    await query.answer()
    await replies.edit(bot, query, *confirm_view(stats, ctx.t))


async def on_delete(query: CallbackQuery, callback_data: HabitCb, ctx: Ctx, bot: Bot) -> None:
    removed = await habits.delete(ctx.session, ctx.user.id, callback_data.id)
    await replies.answer_quietly(query, ctx.t("deleted" if removed else "already-deleted"))
    await replies.edit(bot, query, *habits_view(await _items(ctx, clock()), ctx.t))


async def on_add(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if len(await _items(ctx, clock())) >= LIMITS.habits:
        await query.answer(ctx.t("habits-limit", limit=LIMITS.habits), show_alert=True)
        return
    await query.answer()
    await ctx.state.set_state(HabitForm.name)
    await ctx.state.set_data({"hint": "hint-habit"})
    await replies.send(
        bot, query, ctx.t("habit-ask", limit=LIMITS.habit_length), cancel_menu(ctx.t)
    )


async def save_habit(message: Message, ctx: Ctx) -> None:
    now = clock()
    try:
        habit = await habits.create(ctx.session, ctx.user, message.text or "", now=now)
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
    # Then the goal: a new habit is daily until the user picks fewer days a week.
    stats = await habits.stats_for(ctx.session, ctx.user, habit.id, now=now)
    text, markup = goal_view(stats, ctx.t)
    await message.answer(text, reply_markup=markup)


def create_router() -> Router:
    router = Router(name="habits")
    for action, handler in (
        ("list", on_list),
        ("open", on_open),
        ("map", on_map),
        ("days", on_days),
        ("day", on_day),
        ("goal", on_goal),
        ("setgoal", on_set_goal),
        ("style", on_style),
        ("emoji", on_emoji),
        ("color", on_color),
        ("rename", on_rename),
        ("mark", on_mark),
        ("toggle", on_toggle),
        ("delete", on_delete_menu),
        ("ask", on_ask),
        ("del", on_delete),
        ("add", on_add),
    ):
        router.callback_query.register(handler, HabitCb.filter(F.action == action))
    router.message.register(save_habit, HabitForm.name, F.text)
    router.message.register(save_rename, HabitForm.rename, F.text)
    return router
