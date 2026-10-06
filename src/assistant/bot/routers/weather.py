"""🌤 Weather: now, by the hour and for the week, of the home city and of the extra ones.

A view is built anew at every press, from Open-Meteo's answer cached for ten minutes: the buttons
carry no date, so under an old message they show the weather as of the press."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import CityCb, WeatherCb, preview, weather_views
from assistant.bot.sections import section
from assistant.core.errors import UpstreamUnavailable
from assistant.core.i18n import Translator
from assistant.core.models import User, WeatherCity
from assistant.core.services import cities, weather
from assistant.core.services.weather import Forecast
from assistant.core.timeutil import utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
CITIES_PER_ROW = 3


def weather_markup(
    t: Translator, view: str, city: int, home: str, kept: Sequence[WeatherCity]
) -> InlineKeyboardMarkup:
    """The buttons under a view of `city` (0: the home city, named `home`): the two other views;
    with extra cities, every city for the same view, the home one first, three to a row; then
    «🏙 Города», whose «↩️ Назад» comes back to the home city's weather now."""
    rows = [weather_views(t, view, city)]
    if kept:
        home_button = InlineKeyboardButton(
            text=t("button-city-home", city=preview(home, 20)),
            callback_data=WeatherCb(view=view).pack(),
        )
        places = [home_button] + [
            InlineKeyboardButton(
                text=preview(place.name, 20),
                callback_data=WeatherCb(view=view, city=place.id).pack(),
            )
            for place in kept
        ]
        rows += [
            places[index : index + CITIES_PER_ROW]
            for index in range(0, len(places), CITIES_PER_ROW)
        ]
    sub_view = CityCb(action="list", back="w").pack()
    rows.append([InlineKeyboardButton(text=t("button-cities"), callback_data=sub_view)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def view_text(view: str, forecast: Forecast, now: datetime, user: User, t: Translator) -> str:
    if view == "hours":
        return texts.hours_text(forecast, now, user.timezone, t)
    if view == "week":
        return texts.week_text(forecast, now, t)
    return texts.weather_text(forecast.now, t)


async def weather_view(
    ctx: Ctx, view: str, city: WeatherCity | None, kept: Sequence[WeatherCity]
) -> tuple[str, InlineKeyboardMarkup]:
    """A view of an extra city, or of the home one for None, with its buttons; `kept` is the
    user's list of extra cities. UpstreamUnavailable without the forecast."""
    user = ctx.user
    if city is None:
        forecast = await weather.forecast(ctx.meteo, user.city, user.lat, user.lon)
    else:
        forecast = await weather.forecast(ctx.meteo, city.name, city.lat, city.lon)
    text = view_text(view, forecast, clock(), user, ctx.t)
    shown = city.id if city is not None else 0
    return text, weather_markup(ctx.t, view, shown, user.city, kept)


@section("weather")
async def show_weather(message: Message, ctx: Ctx) -> None:
    kept = await cities.list_for(ctx.session, ctx.user.id)
    try:
        text, markup = await weather_view(ctx, "now", None, kept)
    except UpstreamUnavailable:
        await message.answer(ctx.t("weather-unavailable"))
        return
    await message.answer(text, reply_markup=markup, link_preview_options=replies.NO_PREVIEW)


async def on_view(query: CallbackQuery, callback_data: WeatherCb, ctx: Ctx, bot: Bot) -> None:
    kept = await cities.list_for(ctx.session, ctx.user.id)
    city = next((place for place in kept if place.id == callback_data.city), None)
    # Removed meanwhile (here or in the app), or never the user's: the home city instead.
    gone = callback_data.city != 0 and city is None
    try:
        text, markup = await weather_view(ctx, callback_data.view, city, kept)
    except UpstreamUnavailable:
        # Nothing changes: neither this message nor, under the digest, a new one comes.
        await replies.answer_quietly(query, ctx.t("weather-unavailable"))
        return
    # The forecast may have taken seconds: a query too old to answer must not cost the view.
    await replies.answer_quietly(query, ctx.t("weather-city-gone") if gone else None)
    if callback_data.new:
        # Under the digest or «Мой день», which stay as they are: the view comes on its own,
        # with buttons that change it in place.
        await replies.send(bot, query, text, markup, link_preview_options=replies.NO_PREVIEW)
    else:
        await replies.edit(bot, query, text, markup, link_preview_options=replies.NO_PREVIEW)


def create_router() -> Router:
    router = Router(name="weather")
    router.callback_query.register(on_view, WeatherCb.filter())
    return router
