"""Bot and dispatcher wiring."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram import Bot, Dispatcher, Router
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.bot.db_commit import install_commit_before_request
from assistant.bot.fsm_storage import SqliteStorage
from assistant.bot.middlewares import DbSession, PrivateOnly, UserContext
from assistant.bot.routers import SECTION_ROUTERS, errors, fallback, menu, start
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings


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
) -> Dispatcher:
    # Keyword arguments become workflow data, visible to middlewares as data["meteo"] etc.
    dp = Dispatcher(storage=SqliteStorage(sessionmaker), meteo=meteo, cbr=cbr, settings=settings)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(PrivateOnly())
        observer.outer_middleware(DbSession(sessionmaker))
        observer.outer_middleware(UserContext())
    routers = list(sections) if sections is not None else [make() for make in SECTION_ROUTERS]
    dp.include_routers(
        errors.create_router(),
        start.create_router(),
        menu.create_router(),
        *routers,
        fallback.create_router(),
    )
    return dp
