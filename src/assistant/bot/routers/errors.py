"""Any unhandled exception: log it (token-free) and tell the user something went wrong."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import AiogramError
from aiogram.types import ErrorEvent
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.i18n import resolve_language, translator
from assistant.core.services import users

log = logging.getLogger(__name__)


async def _language(sessionmaker: async_sessionmaker[AsyncSession] | None, tg_user: TgUser) -> str:
    """The language chosen in the settings, else Telegram's; a fresh session, since the
    update's own session is gone (and the database may be what failed)."""
    saved: str | None = None
    if sessionmaker is not None:
        try:
            async with sessionmaker() as session:
                user = await users.get(session, tg_user.id)
                saved = user.language if user is not None else None
        except Exception:
            log.warning("could not read the user's language for the error message")
    return resolve_language(saved, tg_user.language_code)


async def on_error(
    event: ErrorEvent,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
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
    t = translator(await _language(sessionmaker, user))
    if callback_query is not None:
        # Stop the button's loading spinner, since no handler answered the query. A query
        # that is too old to answer must not keep the message below from being sent.
        try:
            await bot.answer_callback_query(callback_query.id)
        except AiogramError as error:
            log.info("could not answer the callback query of the failed update: %s", error)
    try:
        await bot.send_message(chat.id, t("error-generic"))
    except AiogramError:
        log.warning("could not tell user about the failed update")


def create_router() -> Router:
    router = Router(name="errors")
    router.errors.register(on_error)
    return router
