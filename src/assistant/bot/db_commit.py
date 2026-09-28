"""Releases SQLite's write lock before every outgoing Telegram API call.

DbSession (see middlewares.py) keeps one write transaction open per update so a handler's
writes can be committed together, and SqliteStorage's shared mode already commits its own
writes immediately (see fsm_storage.py). But a handler can still write to `ctx.session`
directly (e.g. saving a note) and then send a Telegram message. SQLite allows only one
writer at a time, so if that write's transaction were still open, it would hold the lock
across the network await — a concurrent update (its own asyncio task, its own session) or
the scheduler trying to write in the meantime would then wait out busy_timeout and fail
with "database is locked". This request middleware commits the ambient session, if one is
open and mid-transaction, right before the request goes out, so the lock never survives a
network wait.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType

from assistant.bot.fsm_storage import current_session


class CommitBeforeRequest(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        session = current_session.get()
        if session is not None and session.in_transaction():
            await session.commit()
        return await make_request(bot, method)


def install_commit_before_request(bot: Bot) -> None:
    bot.session.middleware(CommitBeforeRequest())
