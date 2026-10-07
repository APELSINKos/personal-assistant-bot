"""/start, /help, /app, /cancel and the Cancel button — they work from any state."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message

from assistant.bot.context import Ctx
from assistant.bot.keyboards import app_markup, is_cancel, main_menu
from assistant.bot.replies import NO_PREVIEW


async def start(message: Message, ctx: Ctx) -> None:
    await ctx.state.clear()
    name = ctx.user.first_name or ctx.t("friend")
    # The credits name the sites of the data: no preview card of one under the welcome.
    await message.answer(
        ctx.t("welcome", name=name), reply_markup=main_menu(ctx.t), link_preview_options=NO_PREVIEW
    )
    markup = app_markup(ctx.t, ctx.settings.webapp_url)
    if markup is not None:
        await message.answer(ctx.t("app-open"), reply_markup=markup)


async def open_app(message: Message, ctx: Ctx) -> None:
    await ctx.state.clear()
    markup = app_markup(ctx.t, ctx.settings.webapp_url)
    await message.answer(ctx.t("app-open" if markup else "app-soon"), reply_markup=markup)


async def cancel(message: Message, ctx: Ctx) -> None:
    await ctx.state.clear()
    await message.answer(ctx.t("cancelled"), reply_markup=main_menu(ctx.t))


def create_router() -> Router:
    router = Router(name="start")
    router.message.register(start, StateFilter("*"), CommandStart())
    router.message.register(start, StateFilter("*"), Command("help"))
    router.message.register(open_app, StateFilter("*"), Command("app"))
    router.message.register(cancel, StateFilter("*"), Command("cancel"))
    router.message.register(cancel, StateFilter("*"), F.text.func(is_cancel))
    return router
