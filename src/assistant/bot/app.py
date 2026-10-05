"""Bot and dispatcher wiring."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant import __version__
from assistant.bot.db_commit import install_commit_before_request
from assistant.bot.fsm_storage import SqliteStorage
from assistant.bot.middlewares import DbSession, PrivateOnly, UserContext
from assistant.bot.routers import SECTION_ROUTERS, errors, fallback, menu, start
from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings
from assistant.core.ratelimit import RateLimiter

log = logging.getLogger(__name__)


async def announce_start() -> None:
    # Runs inside start_polling right before polling begins. The deploy health check
    # (deploy/assistant-deploy) waits for exactly this phrase — keep it unchanged.
    log.info("Bot started, version %s", __version__)


def drop_rich_messages(content: str) -> Any:
    """Decode a Bot API response without the rich messages in it.

    aiogram 3.31.0 validates rich text through a recursive union with no discriminator, so
    the time grows about twentyfold with every level of nesting: one deeply nested message
    would freeze polling, reminders included, before any handler runs, and again after
    every restart, since the update is never confirmed (aiogram issue #1925). The bot
    never reads rich messages; without the field such a message gets the usual answer to
    anything that is not text. Drop this once aiogram validates rich text in linear time.
    """
    data = json.loads(content)
    pending = [data]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            node.pop("rich_message", None)
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return data


def create_bot(settings: Settings) -> Bot:
    session = AiohttpSession(json_loads=drop_rich_messages)
    bot = Bot(settings.bot_token.get_secret_value(), session=session)
    install_commit_before_request(bot)
    return bot


def build_dispatcher(
    sessionmaker: async_sessionmaker[AsyncSession],
    meteo: OpenMeteoClient,
    cbr: CbrClient,
    settings: Settings,
    sections: Sequence[Router] | None = None,
    *,
    calendars: Calendars,
    attempts: RateLimiter,
    cards: RateLimiter,
) -> Dispatcher:
    # Keyword arguments become workflow data, visible to middlewares as data["meteo"] etc.
    # The error handler reads the user's saved language with its own session from
    # `sessionmaker`, since the update's session is closed by the time it runs.
    dp = Dispatcher(
        storage=SqliteStorage(sessionmaker),
        # One update of a user at a time: a double tap or two quick messages see each other's
        # dialog state instead of racing through it.
        events_isolation=SimpleEventIsolation(),
        sessionmaker=sessionmaker,
        meteo=meteo,
        cbr=cbr,
        calendars=calendars,
        attempts=attempts,
        cards=cards,
        settings=settings,
    )
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(PrivateOnly())
        observer.outer_middleware(DbSession(sessionmaker))
        observer.outer_middleware(UserContext())
    dp.startup.register(announce_start)
    routers = list(sections) if sections is not None else [make() for make in SECTION_ROUTERS]
    dp.include_routers(
        errors.create_router(),
        start.create_router(),
        menu.create_router(),
        *routers,
        fallback.create_router(),
    )
    return dp
