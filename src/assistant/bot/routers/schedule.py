"""🎓 The class schedule: a day and a week of lessons, connecting a source (a MIREA group, a
link, an .ics file), refreshing it, lesson alerts, disconnecting."""

from __future__ import annotations

import io
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import ScheduleCb, cancel_menu, main_menu
from assistant.bot.sections import section
from assistant.bot.states import ScheduleForm
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import ScheduleKind, ScheduleSource
from assistant.core.services import groups, schedule
from assistant.core.services.group_names import MIREA_ZONE
from assistant.core.timeutil import SUPPORTED_YEARS, local_today, to_local, utcnow

Send = Callable[..., Awaitable[object]]
GROUP_QUERY = range(2, 41)  # characters in a group search


async def _download(bot: Bot, file_id: str) -> bytes:
    buffer = io.BytesIO()
    await bot.download(file_id, destination=buffer)
    return buffer.getvalue()


# Replaced in tests: the fake Telegram session serves no files, and the clock is frozen.
download: Callable[[Bot, str], Awaitable[bytes]] = _download
clock: Callable[[], datetime] = utcnow


def _button(text: str, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=ScheduleCb(action=action, value=value).pack()
    )


def _markup(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def connect_view(ctx: Ctx) -> tuple[str, InlineKeyboardMarkup]:
    return ctx.t("schedule-intro"), _markup(
        [_button(ctx.t("button-find-group"), "find")],
        [_button(ctx.t("button-by-link"), "link"), _button(ctx.t("button-by-file"), "file")],
    )


def _stale_since(ctx: Ctx, source: ScheduleSource, now: datetime) -> date | None:
    if not schedule.is_stale(source, now):
        return None
    return to_local(source.ok_at or source.fetched_at, ctx.user.timezone).date()


async def day_view(ctx: Ctx, source: ScheduleSource, day: date) -> tuple[str, InlineKeyboardMarkup]:
    now = clock()
    today = local_today(ctx.user.timezone, now)
    lessons = await schedule.lessons_on(ctx.session, ctx.user, day)
    week = await schedule.week_label(ctx.session, ctx.user.id, day)
    text = texts.schedule_day_text(
        day, today, lessons, week, ctx.user.timezone, ctx.t, _stale_since(ctx, source, now)
    )
    if day == today:
        jump = _button(ctx.t("button-schedule-tomorrow"), "day", str(today + timedelta(days=1)))
    else:
        jump = _button(ctx.t("button-schedule-today"), "day", str(today))
    return text, _markup(
        [
            _button("‹", "day", str(day - timedelta(days=1))),
            jump,
            _button("›", "day", str(day + timedelta(days=1))),
        ],
        [
            _button(ctx.t("button-schedule-week"), "week", str(day)),
            _button(ctx.t("button-schedule-source"), "src"),
        ],
    )


async def week_view(
    ctx: Ctx, source: ScheduleSource, day: date
) -> tuple[str, InlineKeyboardMarkup]:
    monday = day - timedelta(days=day.weekday())
    start, _ = schedule.day_bounds(monday, ctx.user.timezone)
    end, _ = schedule.day_bounds(monday + timedelta(days=7), ctx.user.timezone)
    lessons = await schedule.lessons_between(ctx.session, ctx.user.id, start, end)
    week = await schedule.week_label(ctx.session, ctx.user.id, monday)
    text = texts.schedule_week_text(
        monday, lessons, week, ctx.user.timezone, ctx.t, _stale_since(ctx, source, clock())
    )
    return text, _markup(
        [
            _button("‹", "week", str(monday - timedelta(days=7))),
            _button(ctx.t("button-schedule-day"), "day"),
            _button("›", "week", str(monday + timedelta(days=7))),
        ],
        [_button(ctx.t("button-schedule-source"), "src")],
    )


def source_view(ctx: Ctx, source: ScheduleSource) -> tuple[str, InlineKeyboardMarkup]:
    rows = []
    if source.kind is not ScheduleKind.FILE:  # a file has nothing new to download
        rows.append([_button(ctx.t("button-refresh"), "refresh")])
    rows += [
        [_button(ctx.t("button-lesson-alerts"), "alerts")],
        [_button(ctx.t("button-change-source"), "change")],
        [_button(ctx.t("button-disconnect"), "off")],
        [_button(ctx.t("button-back"), "day")],
    ]
    text = texts.schedule_source_text(source, ctx.user.timezone, clock(), ctx.t)
    return text, _markup(*rows)


def alerts_view(ctx: Ctx, source: ScheduleSource) -> tuple[str, InlineKeyboardMarkup]:
    current = source.lesson_reminder_minutes

    def choice(text: str, value: int | None) -> InlineKeyboardButton:
        mark = "✓ " if value == current else ""
        return _button(mark + text, "alert", str(value or "off"))

    minutes = [choice(ctx.t("button-alerts-minutes", minutes=m), m) for m in schedule.ALERT_MINUTES]
    return ctx.t("schedule-alerts-pick"), _markup(
        [choice(ctx.t("button-alerts-off"), None)],
        minutes[:3],
        minutes[3:],
        [_button(ctx.t("button-back"), "src")],
    )


def _day(value: str, ctx: Ctx) -> date | None:
    """A day from a button; an empty value is today, anything odd is a stale button."""
    if not value:
        return local_today(ctx.user.timezone, clock())
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    return day if day.year in SUPPORTED_YEARS else None


def _is_number(value: str) -> bool:
    """Whether a button's value is a number the bot could have put there: «²» passes isdigit()
    but not int(), and twenty digits overflow an SQLite integer."""
    return value.isascii() and value.isdigit() and len(value) <= 9


@section("schedule")
async def show_schedule(message: Message, ctx: Ctx) -> None:
    source = await schedule.get_source(ctx.session, ctx.user.id)
    if source is None:
        text, markup = connect_view(ctx)
    else:
        text, markup = await day_view(ctx, source, local_today(ctx.user.timezone, clock()))
    await message.answer(text, reply_markup=markup)


async def _source_or_stale(query: CallbackQuery, ctx: Ctx) -> ScheduleSource | None:
    source = await schedule.get_source(ctx.session, ctx.user.id)
    if source is None:
        await replies.answer_quietly(query, ctx.t("stale-button"))
    return source


async def on_day(query: CallbackQuery, callback_data: ScheduleCb, ctx: Ctx, bot: Bot) -> None:
    source = await _source_or_stale(query, ctx)
    day = _day(callback_data.value, ctx)
    if source is None:
        return
    if day is None:
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *await day_view(ctx, source, day))


async def on_week(query: CallbackQuery, callback_data: ScheduleCb, ctx: Ctx, bot: Bot) -> None:
    source = await _source_or_stale(query, ctx)
    day = _day(callback_data.value, ctx)
    if source is None:
        return
    if day is None:
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *await week_view(ctx, source, day))


async def on_source(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    source = await _source_or_stale(query, ctx)
    if source is not None:
        await replies.answer_quietly(query)
        await replies.edit(bot, query, *source_view(ctx, source))


async def on_refresh(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    source = await _source_or_stale(query, ctx)
    if source is None:
        return
    if source.kind is ScheduleKind.FILE:  # a file's view has no such button: it is an old one
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    if schedule.refresh_wait(source, clock()) > 0:
        await replies.answer_quietly(query, ctx.t("schedule-refresh-wait"))
        return
    # Answer first: the download may take seconds, and a pressed button must not spin that long.
    await replies.answer_quietly(query)
    source = await schedule.refresh(ctx.session, ctx.user, ctx.calendars, clock())
    await replies.edit(bot, query, *source_view(ctx, source))


async def on_alerts(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    source = await _source_or_stale(query, ctx)
    if source is not None:
        await replies.answer_quietly(query)
        await replies.edit(bot, query, *alerts_view(ctx, source))


async def on_alert(query: CallbackQuery, callback_data: ScheduleCb, ctx: Ctx, bot: Bot) -> None:
    value = callback_data.value
    minutes = None if value == "off" else int(value) if _is_number(value) else -1
    try:
        source = await schedule.set_alert_minutes(ctx.session, ctx.user.id, minutes)
    except (InvalidInput, NotFound):
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *source_view(ctx, source))


async def on_change(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    # The current source stays until a new one is connected successfully.
    await replies.answer_quietly(query)
    await replies.edit(bot, query, *connect_view(ctx))


async def on_off(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if await _source_or_stale(query, ctx) is None:
        return
    await replies.answer_quietly(query)
    await replies.edit(
        bot,
        query,
        ctx.t("schedule-disconnect-ask"),
        _markup(
            [_button(ctx.t("button-disconnect-yes"), "offyes")],
            [_button(ctx.t("button-back"), "src")],
        ),
    )


async def on_off_yes(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if not await schedule.disconnect(ctx.session, ctx.user.id):
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    await replies.answer_quietly(query, ctx.t("schedule-disconnected"))
    await replies.edit(bot, query, *connect_view(ctx))


async def _connect(send: Send, ctx: Ctx, attempt: Callable[[], Awaitable[ScheduleSource]]) -> None:
    """Run one way of connecting and report it; on failure the dialog stays open to retry."""
    try:
        source = await attempt()
    except NotFound:
        await send(ctx.t("schedule-error-group"))
        return
    except InvalidInput as error:
        await send(texts.schedule_error_text(str(error.params.get("reason", "")), ctx.t))
        return
    await ctx.state.clear()
    now = clock()
    ahead = await schedule.lessons_ahead(ctx.session, ctx.user.id, now)
    title = source.title or ctx.t("schedule-source-untitled")
    key = "schedule-connected" if ahead else "schedule-connected-empty"
    await send(ctx.t(key, title=title, count=ahead), main_menu(ctx.t))
    await send(*await day_view(ctx, source, local_today(ctx.user.timezone, now)))


def _answer(message: Message) -> Send:
    async def send(text: str, markup: replies.Markup = None) -> object:
        return await message.answer(text, reply_markup=markup)

    return send


def _send_to(bot: Bot, query: CallbackQuery) -> Send:
    async def send(text: str, markup: replies.Markup = None) -> object:
        await replies.send(bot, query, text, markup)
        return None

    return send


async def _ask(query: CallbackQuery, ctx: Ctx, bot: Bot, state: State, key: str, hint: str) -> None:
    await replies.answer_quietly(query)
    await ctx.state.set_state(state)
    await ctx.state.set_data({"hint": hint})
    await replies.send(bot, query, ctx.t(key), cancel_menu(ctx.t))


async def on_find(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    if await groups.count(ctx.session) == 0:
        await replies.answer_quietly(query)
        await replies.send(bot, query, ctx.t("schedule-directory-empty"))
        return
    await _ask(query, ctx, bot, ScheduleForm.group, "schedule-ask-group", "hint-group")


async def on_link(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await _ask(query, ctx, bot, ScheduleForm.url, "schedule-ask-link", "hint-link")


async def on_file(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await _ask(query, ctx, bot, ScheduleForm.file, "schedule-ask-file", "hint-file")


async def got_group(message: Message, ctx: Ctx) -> None:
    name = " ".join((message.text or "").split())
    # Whether a semester is still on goes by the section's clock, like every other date here.
    found = (
        await groups.search(ctx.session, name, today=local_today(MIREA_ZONE, clock()))
        if len(name) in GROUP_QUERY
        else []
    )
    if not found:
        # While the first crawl runs, the group may simply not be reached yet.
        building = await groups.building(ctx.session)
        key = "schedule-directory-empty" if building else "schedule-group-not-found"
        await message.answer(ctx.t(key, name=name[:40]))
        return
    if len(found) == 1:
        group_id = found[0].id
        await _connect(
            _answer(message),
            ctx,
            lambda: schedule.connect_mirea(ctx.session, ctx.user, group_id, ctx.calendars, clock()),
        )
        return
    rows = [[_button(group.name, "group", str(group.id))] for group in found]
    await message.answer(ctx.t("schedule-group-choose"), reply_markup=_markup(*rows))


async def on_group(query: CallbackQuery, callback_data: ScheduleCb, ctx: Ctx, bot: Bot) -> None:
    if not _is_number(callback_data.value):
        await replies.answer_quietly(query, ctx.t("stale-button"))
        return
    group_id = int(callback_data.value)
    await replies.answer_quietly(query)
    await replies.drop_buttons(bot, query)
    await _connect(
        _send_to(bot, query),
        ctx,
        lambda: schedule.connect_mirea(ctx.session, ctx.user, group_id, ctx.calendars, clock()),
    )


async def got_link(message: Message, ctx: Ctx) -> None:
    link = (message.text or "").strip()
    await _connect(
        _answer(message),
        ctx,
        lambda: schedule.connect_url(ctx.session, ctx.user, link, ctx.calendars, clock()),
    )


async def got_file(message: Message, ctx: Ctx, bot: Bot) -> None:
    document = message.document
    if document is None:
        return
    # A size Telegram did not report is not taken on trust: the file could be up to 20 MB.
    if document.file_size is None or document.file_size > schedule.FILE_LIMIT:
        await message.answer(texts.schedule_error_text("too_large", ctx.t))
        return
    body = await download(bot, document.file_id)
    await _connect(
        _answer(message),
        ctx,
        lambda: schedule.connect_file(ctx.session, ctx.user, body, document.file_name, clock()),
    )


async def file_expected(message: Message, ctx: Ctx) -> None:
    await message.answer(ctx.t("hint-file"))


def create_router() -> Router:
    router = Router(name="schedule")
    for action, handler in (
        ("day", on_day),
        ("week", on_week),
        ("src", on_source),
        ("refresh", on_refresh),
        ("alerts", on_alerts),
        ("alert", on_alert),
        ("change", on_change),
        ("off", on_off),
        ("offyes", on_off_yes),
        ("find", on_find),
        ("link", on_link),
        ("file", on_file),
    ):
        router.callback_query.register(handler, ScheduleCb.filter(F.action == action))
    # A group button works only while its search is open: a second tap that arrives after the
    # first one connected falls through to the fallback's stale-button answer.
    router.callback_query.register(
        on_group, ScheduleForm.group, ScheduleCb.filter(F.action == "group")
    )
    router.message.register(got_group, ScheduleForm.group, F.text)
    router.message.register(got_link, ScheduleForm.url, F.text)
    router.message.register(got_file, ScheduleForm.file, F.document)
    router.message.register(file_expected, ScheduleForm.file)
    return router
