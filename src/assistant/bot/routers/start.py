"""/start, /help, /app, /cancel and the Cancel button — they work from any state, and so does
the silence on Telegram's service messages."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message

from assistant.bot.context import Ctx
from assistant.bot.keyboards import app_markup, is_cancel, main_menu
from assistant.bot.replies import NO_PREVIEW

# What Telegram itself posts in the chat: a pinned message, the auto-delete timer, the chat's
# wallpaper, the leave to write given in the app. Not UNKNOWN: a rich message comes as one
# (app.drop_rich_messages) and gets the usual answer.
SERVICE = frozenset(
    {
        ContentType.PINNED_MESSAGE,
        ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED,
        ContentType.CHAT_BACKGROUND_SET,
        ContentType.WRITE_ACCESS_ALLOWED,
    }
)


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


async def service_message(message: Message) -> None:
    """Telegram's note of a pin, the auto-delete timer, the wallpaper or the user's leave for the
    bot to write (the app's «allow messages» dialog). UserContext has run as for any message to
    the bot: the bot may write here, and a «blocked» mark is lifted. Nothing to answer: the user
    wrote nothing, and an open dialog goes on."""


def create_router() -> Router:
    router = Router(name="start")
    router.message.register(start, StateFilter("*"), CommandStart())
    router.message.register(start, StateFilter("*"), Command("help"))
    router.message.register(open_app, StateFilter("*"), Command("app"))
    router.message.register(cancel, StateFilter("*"), Command("cancel"))
    router.message.register(cancel, StateFilter("*"), F.text.func(is_cancel))
    # The start router comes first (app.build_dispatcher): no «🤔 Не понял» or «Нужен текст».
    router.message.register(service_message, StateFilter("*"), F.content_type.in_(SERVICE))
    return router
