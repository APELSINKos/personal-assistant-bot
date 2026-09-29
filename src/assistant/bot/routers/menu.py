"""Main menu buttons work from any state and in any supported language."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message

from assistant.bot.context import Ctx
from assistant.bot.keyboards import main_menu, menu_key
from assistant.bot.sections import SECTIONS


async def _open(key: str, message: Message, ctx: Ctx) -> None:
    await ctx.state.clear()
    show = SECTIONS.get(key)
    if show is None:
        await message.answer(ctx.t("unknown"), reply_markup=main_menu(ctx.t))
        return
    await show(message, ctx)


async def open_section(message: Message, ctx: Ctx) -> None:
    await _open(menu_key(message.text) or "", message, ctx)


async def settings_command(message: Message, ctx: Ctx) -> None:
    await _open("settings", message, ctx)


def create_router() -> Router:
    router = Router(name="menu")
    router.message.register(open_section, StateFilter("*"), F.text.func(menu_key))
    router.message.register(settings_command, StateFilter("*"), Command("settings"))
    return router
