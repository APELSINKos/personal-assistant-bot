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
    callback_query = update.callback_query
    if update.message is not None:
        chat, user = update.message.chat, update.message.from_user
    elif callback_query is not None and callback_query.message is not None:
        chat, user = callback_query.message.chat, callback_query.from_user
    else:
        return
    if chat.type != "private" or user is None:
        return
    t = translator(resolve_language(None, user.language_code))
    try:
        if callback_query is not None:
            # Stop the button's loading spinner, since no handler answered the query.
            await bot.answer_callback_query(callback_query.id)
        await bot.send_message(chat.id, t("error-generic"))
    except TelegramAPIError:
        log.warning("could not tell user about the failed update")


def create_router() -> Router:
    router = Router(name="errors")
    router.errors.register(on_error)
    return router
