"""⚙️ Settings: city (with a choice between namesakes), digest time and switch, language."""

from __future__ import annotations

import secrets
from dataclasses import asdict

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import SettingsCb, cancel_menu, main_menu
from assistant.bot.sections import section
from assistant.bot.states import SettingsForm
from assistant.core.clients.openmeteo import City
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, UpstreamUnavailable
from assistant.core.i18n import SUPPORTED, Translator, resolve_language, translator
from assistant.core.models import User
from assistant.core.money_style import CURRENCIES
from assistant.core.services import money, users

AUTO = "auto"
# Joins the search id and the index in a city button's value. Not ":" — that is the
# separator of the packed callback data itself.
PICK_JOIN = "-"


def _button(text: str, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=SettingsCb(action=action, value=value).pack()
    )


def city_label(city: City) -> str:
    parts: list[str] = []
    for part in (city.name, city.admin, city.country):
        if part and part not in parts:
            parts.append(part)
    return ", ".join(parts)


def settings_view(user: User, t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    current = translator(resolve_language(user.language, user.tg_language))("language-name")
    language = (
        t("settings-language", language=current)
        if user.language
        else t("settings-language-auto", language=current)
    )
    text = "\n".join(
        [
            t("settings-title"),
            "",
            t("settings-city", city=user.city),
            t("settings-morning-on" if user.morning_enabled else "settings-morning-off"),
            t("settings-time", time=user.morning_time),
            language,
            t("settings-currency", sign=_sign(user.currency), code=user.currency),
        ]
    )
    toggle = "button-morning-off" if user.morning_enabled else "button-morning-on"
    rows = [
        [_button(t("weather-change-city"), "city"), _button(t("button-time"), "time")],
        [_button(t(toggle), "toggle")],
        [_button(t("button-language"), "lang"), _button(t("button-currency"), "currency")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _sign(code: str) -> str:
    return CURRENCIES[code].sign if code in CURRENCIES else code


def currency_view(t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    buttons = [_button(f"{_sign(code)} {code}", "setcurrency", code) for code in CURRENCIES]
    rows = [buttons[index : index + 4] for index in range(0, len(buttons), 4)]
    rows.append([_button(t("button-back"), "back")])
    return t("currency-pick"), InlineKeyboardMarkup(inline_keyboard=rows)


def language_view(t: Translator) -> tuple[str, InlineKeyboardMarkup]:
    rows = [[_button(translator(code)("language-button"), "setlang", code)] for code in SUPPORTED]
    rows.append([_button(t("language-auto"), "setlang", AUTO)])
    rows.append([_button(t("button-back"), "back")])
    return t("language-pick"), InlineKeyboardMarkup(inline_keyboard=rows)


@section("settings")
async def show_settings(message: Message, ctx: Ctx) -> None:
    text, markup = settings_view(ctx.user, ctx.t)
    await message.answer(text, reply_markup=markup)


async def on_back(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *settings_view(ctx.user, ctx.t))


async def on_toggle(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await users.set_morning(ctx.session, ctx.user, enabled=not ctx.user.morning_enabled)
    await query.answer()
    await replies.edit(bot, query, *settings_view(ctx.user, ctx.t))


async def on_language_menu(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *language_view(ctx.t))


async def on_set_language(
    query: CallbackQuery,
    callback_data: SettingsCb,
    ctx: Ctx,
    bot: Bot,
) -> None:
    value = callback_data.value
    if value != AUTO and value not in SUPPORTED:
        await query.answer(ctx.t("stale-button"))
        return
    await users.set_language(ctx.session, ctx.user, None if value == AUTO else value)
    t = translator(resolve_language(ctx.user.language, ctx.user.tg_language))
    await query.answer()
    await replies.edit(bot, query, *settings_view(ctx.user, t))
    # The reply keyboard can only be replaced by sending a new message with it.
    await replies.send(bot, query, t("language-changed", language=t("language-name")), main_menu(t))


async def on_currency_menu(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *currency_view(ctx.t))


async def on_set_currency(
    query: CallbackQuery, callback_data: SettingsCb, ctx: Ctx, bot: Bot
) -> None:
    """Only the sign of the amounts changes: the entries keep their numbers."""
    if callback_data.value not in CURRENCIES:
        await query.answer(ctx.t("stale-button"))
        return
    await money.set_currency(ctx.session, ctx.user, callback_data.value)
    await query.answer(ctx.t("currency-changed", sign=_sign(callback_data.value)))
    await replies.edit(bot, query, *settings_view(ctx.user, ctx.t))


async def on_city(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await ctx.state.set_state(SettingsForm.city)
    await ctx.state.set_data({"hint": "hint-city"})
    await replies.send(bot, query, ctx.t("city-ask"), cancel_menu(ctx.t))


async def _save_city(ctx: Ctx, city: City) -> bool:
    try:
        await users.set_city(ctx.session, ctx.user, city.name, city.lat, city.lon, city.timezone)
    except InvalidInput:
        return False
    await ctx.state.clear()
    return True


async def got_city(message: Message, ctx: Ctx) -> None:
    name = (message.text or "").strip()
    if not 1 <= len(name) <= LIMITS.city_length:
        await message.answer(ctx.t("city-bad-name", limit=LIMITS.city_length))
        return
    try:
        found = await ctx.meteo.search(name, ctx.lang)
    except UpstreamUnavailable:
        await ctx.state.clear()
        await message.answer(ctx.t("city-unavailable"), reply_markup=main_menu(ctx.t))
        return
    if len(found) == 1 and await _save_city(ctx, found[0]):
        await message.answer(ctx.t("city-saved", city=found[0].name), reply_markup=main_menu(ctx.t))
        return
    if len(found) > 1:
        # A new id per search: a button from an earlier list must not pick from this one.
        search = secrets.token_hex(4)
        await ctx.state.update_data(search=search, cities=[asdict(city) for city in found])
        rows = [
            [_button(city_label(city), "pick", f"{search}{PICK_JOIN}{index}")]
            for index, city in enumerate(found)
        ]
        await message.answer(
            ctx.t("city-choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        return
    await message.answer(ctx.t("city-not-found", name=name))


async def on_pick(query: CallbackQuery, callback_data: SettingsCb, ctx: Ctx, bot: Bot) -> None:
    data = await ctx.state.get_data()
    search, _, index = callback_data.value.partition(PICK_JOIN)
    city: City | None = None
    if search and search == data.get("search"):  # a button from an older list is stale
        try:
            city = City(**data["cities"][int(index)])
        except (TypeError, ValueError, LookupError):
            city = None
    if city is None or not await _save_city(ctx, city):
        await query.answer(ctx.t("stale-button"))
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    await replies.send(bot, query, ctx.t("city-saved", city=city.name), main_menu(ctx.t))


async def on_time(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await ctx.state.set_state(SettingsForm.time)
    await ctx.state.set_data({"hint": "hint-time"})
    await replies.send(bot, query, ctx.t("time-ask"), cancel_menu(ctx.t))


async def got_time(message: Message, ctx: Ctx) -> None:
    try:
        await users.set_morning(ctx.session, ctx.user, time=message.text or "")
    except InvalidInput:
        await message.answer(ctx.t("time-bad"))
        return
    await ctx.state.clear()
    await message.answer(
        ctx.t("time-saved", time=ctx.user.morning_time), reply_markup=main_menu(ctx.t)
    )


def create_router() -> Router:
    router = Router(name="settings")
    router.callback_query.register(on_currency_menu, SettingsCb.filter(F.action == "currency"))
    router.callback_query.register(on_set_currency, SettingsCb.filter(F.action == "setcurrency"))
    for action, handler in (
        ("back", on_back),
        ("toggle", on_toggle),
        ("lang", on_language_menu),
        ("setlang", on_set_language),
        ("city", on_city),
        ("pick", on_pick),
        ("time", on_time),
    ):
        router.callback_query.register(handler, SettingsCb.filter(F.action == action))
    router.message.register(got_city, SettingsForm.city, F.text)
    router.message.register(got_time, SettingsForm.time, F.text)
    return router
