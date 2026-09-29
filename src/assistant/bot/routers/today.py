"""📅 My day: everything important for today in one message."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from assistant.bot import texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import app_markup
from assistant.bot.sections import section
from assistant.core.services import digest


@section("today")
async def show_today(message: Message, ctx: Ctx) -> None:
    data = await digest.today(ctx.session, ctx.user, ctx.meteo, ctx.cbr)
    name = ctx.user.first_name or ctx.t("friend")
    await message.answer(
        texts.today_text(data, name, ctx.t), reply_markup=app_markup(ctx.t, ctx.settings.webapp_url)
    )


def create_router() -> Router:
    return Router(name="today")
