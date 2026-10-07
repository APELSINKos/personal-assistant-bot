"""📅 My day: everything important for today in one message."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from aiogram import Router
from aiogram.types import Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import today_markup
from assistant.bot.sections import section
from assistant.core.services import digest
from assistant.core.timeutil import utcnow

# Replaced in tests to freeze time.
clock: Callable[[], datetime] = utcnow


@section("today")
async def show_today(message: Message, ctx: Ctx) -> None:
    data = await digest.today(ctx.session, ctx.user, ctx.meteo, ctx.cbr, clock())
    name = ctx.user.first_name or ctx.t("friend")
    await message.answer(
        texts.today_text(data, name, ctx.t),
        reply_markup=today_markup(ctx.t, data.weather is not None, ctx.settings.webapp_url),
        link_preview_options=replies.NO_PREVIEW,
    )


def create_router() -> Router:
    return Router(name="today")
