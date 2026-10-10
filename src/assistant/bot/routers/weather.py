"""🌤 Weather: now, by the hour and for the week, of the home city and of the extra ones, and the
week as a picture.

A view is built anew at every press, from Open-Meteo's answer cached for ten minutes: the buttons
carry no date, so under an old message they show the weather as of the press."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime

from aiogram import Bot, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import CityCb, WeatherCardCb, WeatherCb, preview, weather_views
from assistant.bot.sections import section
from assistant.core.errors import NotFound, UpstreamUnavailable
from assistant.core.i18n import Translator
from assistant.core.models import User, WeatherCity
from assistant.core.services import cities, forecast_cards, weather
from assistant.core.services.weather import Forecast
from assistant.core.timeutil import utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow
CITIES_PER_ROW = 3


def weather_markup(
    t: Translator, view: str, city: int, home: str, kept: Sequence[WeatherCity]
) -> InlineKeyboardMarkup:
    """The buttons under a view of `city` (0: the home city, named `home`): the two other views,
    and under the week «🖼 Картинка», the same week as a picture; with extra cities, every city
    for the same view, the home one first, three to a row; then «🏙 Города», whose «↩️ Назад»
    comes back to the home city's weather now."""
    first = weather_views(t, view, city)
    if view == "week":
        picture = WeatherCardCb(city=city).pack()
        first.append(InlineKeyboardButton(text=t("button-weather-card"), callback_data=picture))
    rows = [first]
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
    forecast = await _forecast(ctx, city)
    text = view_text(view, forecast, clock(), ctx.user, ctx.t)
    shown = city.id if city is not None else 0
    return text, weather_markup(ctx.t, view, shown, ctx.user.city, kept)


async def _forecast(ctx: Ctx, city: WeatherCity | None) -> Forecast:
    """The forecast of an extra city, or of the home one for None, on the user's budget: a place
    asked for less than ten minutes ago costs no request. UpstreamUnavailable without it."""
    user = ctx.user
    if city is None:
        return await weather.forecast(ctx.meteo, user.city, user.lat, user.lon, user_id=user.id)
    return await weather.forecast(ctx.meteo, city.name, city.lat, city.lon, user_id=user.id)


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


async def on_card(query: CallbackQuery, callback_data: WeatherCardCb, ctx: Ctx, bot: Bot) -> None:
    """«🖼 Картинка» under the week: the same days as a picture, to forward anywhere. The message
    with the week stays as it is."""
    city: WeatherCity | None = None
    if callback_data.city != 0:
        try:
            city = await cities.get(ctx.session, ctx.user.id, callback_data.city)
        except NotFound:  # removed meanwhile (here or in the app), or never the user's
            await replies.answer_quietly(query, ctx.t("weather-city-gone"))
            return
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    try:
        # Mostly the forecast the week was just drawn from, still kept: no request.
        forecast = await _forecast(ctx, city)
    except UpstreamUnavailable:
        await replies.answer_quietly(query, ctx.t("weather-unavailable"))
        return
    me = await bot.me()
    card = forecast_cards.card_for(forecast, clock(), me.username or "")
    if card is None:
        await replies.answer_quietly(query, ctx.t("weather-days-none"))
        return
    # The forecast may have taken seconds: a query too old to answer must not cost the picture.
    await replies.answer_quietly(query)
    image = await forecast_cards.draw_card(card, ctx.t)
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="forecast.jpg"),
        caption=forecast_cards.caption(card, ctx.t),
    )


def create_router() -> Router:
    router = Router(name="weather")
    router.callback_query.register(on_view, WeatherCb.filter())
    router.callback_query.register(on_card, WeatherCardCb.filter())
    return router
