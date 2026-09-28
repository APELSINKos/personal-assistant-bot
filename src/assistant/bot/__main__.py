"""Entry point: python -m assistant.bot"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from assistant import __version__
from assistant.bot.app import build_dispatcher, create_bot
from assistant.bot.scheduler import Scheduler
from assistant.bot.setup import configure
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import get_settings
from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.logging import setup_logging

log = logging.getLogger("assistant.bot")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, [settings.bot_token.get_secret_value()])
    # One shared engine/sessionmaker for the bot and (Task 13) the scheduler — the
    # write-lock handling in middlewares.py/fsm_storage.py/db_commit.py assumes there's
    # only one.
    engine = create_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    async with httpx.AsyncClient(timeout=settings.http_timeout) as http:
        bot = create_bot(settings)
        meteo, cbr = OpenMeteoClient(http), CbrClient(http)
        dp = build_dispatcher(sessionmaker, meteo, cbr, settings)
        scheduler = Scheduler(bot, sessionmaker, meteo, cbr, interval=settings.scheduler_interval)
        background = asyncio.create_task(scheduler.run(), name="scheduler")
        try:
            await configure(bot, settings)
            log.info("Bot started, version %s", __version__)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            background.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await background
            await bot.session.close()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
