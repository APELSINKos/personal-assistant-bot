"""Last resort: non-text input inside a dialog, anything unknown outside it, stale buttons."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from assistant.bot.context import Ctx
from assistant.bot.keyboards import main_menu


async def unknown(message: Message, ctx: Ctx) -> None:
    text = f"{ctx.t('unknown')}\n{ctx.t('unknown-hint')}"
    await message.answer(text, reply_markup=main_menu(ctx.t))


async def need_text(message: Message, ctx: Ctx) -> None:
    hint_key = (await ctx.state.get_data()).get("hint")
    await message.answer(ctx.t("need-text", hint=ctx.t(hint_key) if hint_key else ""))


async def orphan_state(message: Message, ctx: Ctx) -> None:
    # A state no router handles any more (e.g. after an update): start over.
    await ctx.state.clear()
    await unknown(message, ctx)


async def stale_button(query: CallbackQuery, ctx: Ctx) -> None:
    await query.answer(ctx.t("stale-button"))


def create_router() -> Router:
    router = Router(name="fallback")
    router.message.register(unknown, StateFilter(None))
    router.message.register(need_text, ~F.text)
    router.message.register(orphan_state)
    router.callback_query.register(stale_button)
    return router
