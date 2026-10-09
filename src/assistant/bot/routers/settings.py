"""⚙️ Settings: the cities of the weather (the home city with a choice between namesakes, the
extra ones), digest time and switch, language, currency."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)

from assistant.bot import replies
from assistant.bot.context import Ctx
from assistant.bot.keyboards import CityCb, SettingsCb, WeatherCb, cancel_menu, main_menu, preview
from assistant.bot.sections import section
from assistant.bot.states import SettingsForm
from assistant.core.clients.openmeteo import City
from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound, UpstreamUnavailable
from assistant.core.i18n import SUPPORTED, Translator, resolve_language, translator
from assistant.core.models import User, WeatherCity
from assistant.core.money_style import CURRENCIES
from assistant.core.services import cities, money, users

AUTO = "auto"
# Joins the search id and the index in a city button's value. Not ":" — that is the
# separator of the packed callback data itself.
PICK_JOIN = "-"
# The data keys of a choice between namesakes: the search's id and the places found. Each
# dialog has its own, so a choice made while adding a city never sets the home one.
HOME_CHOICE = ("search", "cities")
ADD_CHOICE = ("add_search", "add_cities")


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
    cities_button = InlineKeyboardButton(
        text=t("button-cities"), callback_data=CityCb(action="list", back="s").pack()
    )
    rows = [
        [cities_button, _button(t("button-time"), "time")],
        [_button(t(toggle), "toggle")],
        [_button(t("button-language"), "lang"), _button(t("button-currency"), "currency")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def cities_view(
    user: User, kept: Sequence[WeatherCity], back: str, t: Translator
) -> tuple[str, InlineKeyboardMarkup]:
    """«🏙 Города»: the home city and the extra ones, a button to remove each, «➕» while there is
    room. `back` tells where the sub-view was opened from, where «↩️ Назад» leads; its buttons
    carry it along, so a redrawn sub-view still knows."""
    lines = [t("cities-title"), "", t("cities-home", city=user.city), ""]
    if kept:
        lines += [t("cities-item", city=city.name) for city in kept]
    else:
        lines.append(t("cities-none", limit=LIMITS.cities))
    removals = [
        InlineKeyboardButton(
            text=t("button-delete-city", city=preview(city.name, 20)),
            callback_data=CityCb(action="del", id=city.id, back=back).pack(),
        )
        for city in kept
    ]
    rows = [[_button(t("button-change-home"), "city")]]
    rows += [removals[index : index + 2] for index in range(0, len(removals), 2)]
    if len(kept) < LIMITS.cities:
        add = CityCb(action="add", back=back).pack()
        rows.append([InlineKeyboardButton(text=t("button-add-city"), callback_data=add)])
    if back == "w":  # the home city's weather now; without the forecast the sub-view stays
        way_back = WeatherCb(view="now").pack()
        rows.append([InlineKeyboardButton(text=t("button-back"), callback_data=way_back)])
    else:
        rows.append([_button(t("button-back"), "back")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


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
    await replies.answer_quietly(query)  # saved: an expired query must not hide it
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
    await replies.answer_quietly(query)
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
    await replies.answer_quietly(query, ctx.t("currency-changed", sign=_sign(callback_data.value)))
    await replies.edit(bot, query, *settings_view(ctx.user, ctx.t))


async def on_city(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await ctx.state.set_state(SettingsForm.city)
    await ctx.state.set_data({"hint": "hint-city"})
    await replies.send(bot, query, ctx.t("city-ask"), cancel_menu(ctx.t))


async def _save_city(ctx: Ctx, city: City) -> bool:
    try:
        # With the GeoNames id an extra city that becomes the home one leaves the list even
        # when today's search puts it a little off the kept point.
        await users.set_city(
            ctx.session,
            ctx.user,
            city.name,
            city.lat,
            city.lon,
            city.timezone,
            geo_id=city.geo_id,
        )
    except InvalidInput:
        return False
    await ctx.state.clear()
    return True


async def _searched(message: Message, ctx: Ctx) -> tuple[str, list[City]] | None:
    """The typed name and the places found for it — one step for the home city and for a city
    to add. None when it has answered already: the name is empty or too long (the dialog waits
    for another), or the search is unavailable (the dialog is over)."""
    name = (message.text or "").strip()
    if not 1 <= len(name) <= LIMITS.city_length:
        await message.answer(ctx.t("city-bad-name", limit=LIMITS.city_length))
        return None
    try:
        found = await ctx.meteo.search(name, ctx.lang, user_id=ctx.user.id)
    except UpstreamUnavailable:
        await ctx.state.clear()
        await message.answer(ctx.t("city-unavailable"), reply_markup=main_menu(ctx.t))
        return None
    return name, found


async def _offer(ctx: Ctx, found: Sequence[City], keys: tuple[str, str]) -> str:
    """Keep the places of a choice under the dialog's keys and return the id of this search,
    which its buttons carry."""
    # A new id per search: a button from an earlier list must not pick from this one.
    search = secrets.token_hex(4)
    search_key, list_key = keys
    await ctx.state.update_data({search_key: search, list_key: [asdict(city) for city in found]})
    return search


def _chosen(
    data: dict[str, Any], search: str, index: str | int, keys: tuple[str, str]
) -> City | None:
    """The place a choice button names, or None for a button of an older list or one that
    names no place of it."""
    search_key, list_key = keys
    if not search or search != data.get(search_key):  # a button from an older list is stale
        return None
    try:
        return City(**data[list_key][int(index)])
    except (TypeError, ValueError, LookupError):
        return None


async def got_city(message: Message, ctx: Ctx) -> None:
    searched = await _searched(message, ctx)
    if searched is None:
        return
    name, found = searched
    if len(found) == 1 and await _save_city(ctx, found[0]):
        await message.answer(ctx.t("city-saved", city=found[0].name), reply_markup=main_menu(ctx.t))
        return
    if len(found) > 1:
        search = await _offer(ctx, found, HOME_CHOICE)
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
    search, _, index = callback_data.value.partition(PICK_JOIN)
    city = _chosen(await ctx.state.get_data(), search, index, HOME_CHOICE)
    if city is None or not await _save_city(ctx, city):
        await query.answer(ctx.t("stale-button"))
        return
    await query.answer()
    await replies.drop_buttons(bot, query)
    await replies.send(bot, query, ctx.t("city-saved", city=city.name), main_menu(ctx.t))


async def _cities_view(ctx: Ctx, back: str) -> tuple[str, InlineKeyboardMarkup]:
    return cities_view(ctx.user, await cities.list_for(ctx.session, ctx.user.id), back, ctx.t)


async def on_cities(query: CallbackQuery, callback_data: CityCb, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await replies.edit(bot, query, *await _cities_view(ctx, callback_data.back))


async def on_delete_city(query: CallbackQuery, callback_data: CityCb, ctx: Ctx, bot: Bot) -> None:
    """At once, without a question: a city is easy to add again."""
    try:
        await cities.delete(ctx.session, ctx.user.id, callback_data.id)
    except NotFound:  # removed already: in the app or from an older sub-view
        await replies.answer_quietly(query, ctx.t("weather-city-gone"))
    else:
        await replies.answer_quietly(query, ctx.t("deleted"))
    await replies.edit(bot, query, *await _cities_view(ctx, callback_data.back))


async def on_add_city(query: CallbackQuery, callback_data: CityCb, ctx: Ctx, bot: Bot) -> None:
    kept = await cities.list_for(ctx.session, ctx.user.id)
    if len(kept) >= LIMITS.cities:
        # The button of a sub-view drawn before the list filled up (in the app, say).
        await query.answer(ctx.t("cities-limit", limit=LIMITS.cities), show_alert=True)
        await replies.edit(bot, query, *cities_view(ctx.user, kept, callback_data.back, ctx.t))
        return
    await query.answer()
    await ctx.state.set_state(SettingsForm.add_city)
    await ctx.state.set_data({"hint": "hint-city-add"})
    await replies.send(bot, query, ctx.t("city-add-ask"), cancel_menu(ctx.t))


async def _add_city(ctx: Ctx, city: City) -> tuple[str, ReplyKeyboardMarkup | None] | None:
    """Put a found place on the list. The reply comes with the main menu when the dialog is
    over: the city is added, or there is no room (the list filled up in the app meanwhile).
    Without it when the place is on the list already or is the home city: the dialog waits
    for another name. None for a place that cannot be kept."""
    try:
        added = await cities.add(ctx.session, ctx.user, city)
    except LimitReached:
        await ctx.state.clear()
        return ctx.t("cities-limit", limit=LIMITS.cities), main_menu(ctx.t)
    except InvalidInput as error:
        if error.params.get("reason") == "duplicate":
            return ctx.t("city-duplicate"), None
        return None
    await ctx.state.clear()
    return ctx.t("city-added", city=added.name), main_menu(ctx.t)


async def got_added_city(message: Message, ctx: Ctx) -> None:
    """A city to add, searched for as the home one. The choice keeps its own data keys and
    buttons: the home city's would make the chosen place the new home."""
    if len(await cities.list_for(ctx.session, ctx.user.id)) >= LIMITS.cities:
        # The list filled up in the app while the question waited: nothing can be added, so
        # nothing is searched for. If it fills up during the search, cities.add refuses.
        await ctx.state.clear()
        await message.answer(
            ctx.t("cities-limit", limit=LIMITS.cities), reply_markup=main_menu(ctx.t)
        )
        return
    searched = await _searched(message, ctx)
    if searched is None:
        return
    name, found = searched
    if len(found) > 1:
        search = await _offer(ctx, found, ADD_CHOICE)
        rows = [
            [
                InlineKeyboardButton(
                    text=city_label(city),
                    callback_data=CityCb(action="pick", id=index, token=search).pack(),
                )
            ]
            for index, city in enumerate(found)
        ]
        await message.answer(
            ctx.t("city-choose-add"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        return
    reply = await _add_city(ctx, found[0]) if found else None
    if reply is None:  # nothing found, or nothing that can be kept
        await message.answer(ctx.t("city-not-found", name=name))
        return
    text, markup = reply
    await message.answer(text, reply_markup=markup)


async def on_pick_city(query: CallbackQuery, callback_data: CityCb, ctx: Ctx, bot: Bot) -> None:
    data = await ctx.state.get_data()
    city = _chosen(data, callback_data.token, callback_data.id, ADD_CHOICE)
    if city is None:
        await query.answer(ctx.t("stale-button"))
        return
    reply = await _add_city(ctx, city)
    await replies.answer_quietly(query)
    if reply is None:
        # A place the server cannot keep (its zone left the server's tzdb after the search,
        # say) counts as not found: the dialog waits for a name, and the choice stays.
        await replies.send(bot, query, ctx.t("city-not-found", name=city.name))
        return
    text, markup = reply
    if markup is not None:  # the dialog is over, and the choice with it
        await replies.drop_buttons(bot, query)
    await replies.send(bot, query, text, markup)


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
    router.callback_query.register(on_cities, CityCb.filter(F.action == "list"))
    router.callback_query.register(on_add_city, CityCb.filter(F.action == "add"))
    router.callback_query.register(on_delete_city, CityCb.filter(F.action == "del"))
    router.callback_query.register(on_pick_city, CityCb.filter(F.action == "pick"))
    router.message.register(got_city, SettingsForm.city, F.text)
    router.message.register(got_time, SettingsForm.time, F.text)
    router.message.register(got_added_city, SettingsForm.add_city, F.text)
    return router
