"""Private-chat guard, one DB session per update, user + translator injection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.bot.context import Ctx
from assistant.bot.fsm_storage import current_session
from assistant.core.i18n import resolve_language, translator
from assistant.core.services import users

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class PrivateOnly(BaseMiddleware):
    """The bot works in private chats only; anything else is dropped before touching the DB."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat: Chat | None = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message is not None:
            chat = event.message.chat
        if chat is None or chat.type != "private":
            return None
        return await handler(event, data)


class DbSession(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self._sessionmaker() as session:
            data["session"] = session
            # Let SqliteStorage and CommitBeforeRequest (db_commit.py) reuse this session
            # for the rest of the update, instead of racing it for SQLite's one write
            # lock with a second connection (see fsm_storage.current_session).
            token = current_session.set(session)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            finally:
                current_session.reset(token)


class UserContext(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return None
        session: AsyncSession = data["session"]
        user = await users.ensure(session, tg_user.id, tg_user.first_name, tg_user.language_code)
        # Release SQLite's write lock now rather than holding it through the handler's
        # network awaits (Telegram sends, and in later tasks Open-Meteo/CBR requests);
        # a cheap no-op when ensure() found nothing to change. expire_on_commit=False on
        # the sessionmaker keeps `user`'s attributes usable after this commit.
        await session.commit()
        data["ctx"] = Ctx(
            session=session,
            user=user,
            t=translator(resolve_language(user.language, user.tg_language)),
            state=data["state"],
            meteo=data["meteo"],
            cbr=data["cbr"],
            settings=data["settings"],
        )
        return await handler(event, data)
