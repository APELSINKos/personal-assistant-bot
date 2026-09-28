"""Any unhandled exception: log it (token-free) and tell the user something went wrong."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from assistant.core.i18n import resolve_language, translator

log = logging.getLogger(__name__)


async def on_error(event: ErrorEvent, bot: Bot) -> None:
    log.error("update %s failed", event.update.update_id, exc_info=event.exception)
    update = event.update
    if update.message is not None:
        chat, user = update.message.chat, update.message.from_user
    elif update.callback_query is not None and update.callback_query.message is not None:
        chat, user = update.callback_query.message.chat, update.callback_query.from_user
    else:
        return
    if chat.type != "private" or user is None:
        return
    t = translator(resolve_language(None, user.language_code))
    try:
        await bot.send_message(chat.id, t("error-generic"))
    except TelegramAPIError:
        log.warning("could not tell user about the failed update")


def create_router() -> Router:
    router = Router(name="errors")
    router.errors.register(on_error)
    return router
