"""Bot and dispatcher wiring."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, Dispatcher, Router
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


def create_bot(settings: Settings) -> Bot:
    bot = Bot(settings.bot_token.get_secret_value())
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
