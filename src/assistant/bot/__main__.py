"""Entry point: python -m assistant.bot"""

from __future__ import annotations

import asyncio
import logging

import httpx

from assistant.bot.app import build_dispatcher, create_bot
from assistant.bot.directory import DirectoryCrawler
from assistant.bot.scheduler import Scheduler
from assistant.bot.setup import configure
from assistant.core.clients.calendars import CalendarFetcher, calendar_client
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import get_settings
from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import check_translations
from assistant.core.logging import setup_logging

log = logging.getLogger("assistant.bot")
SHUTDOWN_GRACE = 15  # seconds the scheduler gets to finish its current tick


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, [settings.bot_token.get_secret_value()])
    check_translations()
    # One shared engine/sessionmaker for the bot and (Task 13) the scheduler — the
    # write-lock handling in middlewares.py/fsm_storage.py/db_commit.py assumes there's
    # only one.
    engine = create_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    async with (
        httpx.AsyncClient(timeout=settings.http_timeout) as http,
        calendar_client() as calendar_http,
    ):
        bot = create_bot(settings)
        meteo, cbr = OpenMeteoClient(http), CbrClient(http)
        calendars = CalendarFetcher(calendar_http)
        dp = build_dispatcher(sessionmaker, meteo, cbr, settings, calendars=calendars)
        scheduler = Scheduler(
            bot, sessionmaker, meteo, cbr, interval=settings.scheduler_interval, calendars=calendars
        )
        crawler = DirectoryCrawler(sessionmaker, calendars) if settings.mirea_directory else None
        background = [asyncio.create_task(scheduler.run(), name="scheduler")]
        if crawler is not None:
            background.append(asyncio.create_task(crawler.run(), name="mirea-directory"))
        try:
            await configure(bot, settings)
            # "Bot started" is logged by a startup handler (app.announce_start) inside
            # start_polling, right before polling begins.
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            try:
                # Let the current tick and crawl request finish their writes; cancel only if
                # they hang.
                scheduler.stop()
                if crawler is not None:
                    crawler.stop()
                await asyncio.wait_for(asyncio.gather(*background), SHUTDOWN_GRACE)
            except TimeoutError:
                log.warning("background tasks did not stop in %d s, cancelled", SHUTDOWN_GRACE)
            except Exception:
                log.exception("a background task ended with an error")
            finally:
                await bot.session.close()
                await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
