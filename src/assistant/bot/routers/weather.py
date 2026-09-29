"""🌤 Weather: current conditions with tips for the user's city."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import SettingsCb
from assistant.bot.sections import section
from assistant.core.errors import UpstreamUnavailable
from assistant.core.i18n import Translator
from assistant.core.services import weather


def city_markup(t: Translator) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        text=t("weather-change-city"), callback_data=SettingsCb(action="city").pack()
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


@section("weather")
async def show_weather(message: Message, ctx: Ctx) -> None:
    try:
        now = await weather.current(ctx.meteo, ctx.user.city, ctx.user.lat, ctx.user.lon)
    except UpstreamUnavailable:
        await message.answer(ctx.t("weather-unavailable"))
        return
    await message.answer(texts.weather_text(now, ctx.t), reply_markup=city_markup(ctx.t))


def create_router() -> Router:
    # The section has no buttons of its own: "change city" is handled by settings.
    return Router(name="weather")
