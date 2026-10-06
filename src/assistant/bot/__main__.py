"""Entry point: python -m assistant.bot"""

from __future__ import annotations

import asyncio
import logging

import httpx
from aiogram import Bot

from assistant.bot.app import build_dispatcher, create_bot
from assistant.bot.directory import DirectoryCrawler
from assistant.bot.scheduler import Scheduler
from assistant.bot.setup import configure
from assistant.core.clients.calendars import CalendarFetcher, calendar_client
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings, get_settings
from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import check_translations
from assistant.core.logging import setup_logging
from assistant.core.services import card_kit, schedule

log = logging.getLogger("assistant.bot")
# Seconds the background work gets to finish on shutdown: the scheduler's current tick, the
# schedule refresh pass in flight and the directory crawler's current request.
SHUTDOWN_GRACE = 15
# Seconds the bot's profile (name, commands, descriptions, menu button) gets in all. It is set
# beside polling: when Telegram does not answer, its requests take 40 s and more, and the
# deploy waits only 30 s for "Bot started".
CONFIGURE_TIMEOUT = 120


async def configure_profile(bot: Bot, settings: Settings) -> None:
    """configure() as a background task: given up after CONFIGURE_TIMEOUT, and an error in it
    costs a log line, never polling."""
    try:
        async with asyncio.timeout(CONFIGURE_TIMEOUT):
            await configure(bot, settings)
    except TimeoutError:
        log.warning("the bot profile was not updated in %s s, given up", CONFIGURE_TIMEOUT)
    except Exception:
        log.exception("could not update the bot profile")


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
        # A forecast call gets the HTTP timeout in all, the wait for a slot included.
        meteo = OpenMeteoClient(http, deadline=settings.http_timeout)
        cbr = CbrClient(http)
        calendars = CalendarFetcher(calendar_http)
        dp = build_dispatcher(
            sessionmaker,
            meteo,
            cbr,
            settings,
            calendars=calendars,
            attempts=schedule.attempt_limiter(),
            cards=card_kit.card_limiter(),
        )
        scheduler = Scheduler(
            bot, sessionmaker, meteo, cbr, interval=settings.scheduler_interval, calendars=calendars
        )
        crawler = DirectoryCrawler(sessionmaker, calendars) if settings.mirea_directory else None
        background = [asyncio.create_task(scheduler.run(), name="scheduler")]
        if crawler is not None:
            background.append(asyncio.create_task(crawler.run(), name="mirea-directory"))
        profile = asyncio.create_task(configure_profile(bot, settings), name="bot-profile")
        try:
            # "Bot started" is logged by a startup handler (app.announce_start) inside
            # start_polling, right before polling begins. The bot's session outlives polling:
            # the profile and the background work may still be using it, so it is closed
            # below, after them, not by aiogram as polling stops.
            await dp.start_polling(
                bot, allowed_updates=dp.resolve_used_update_types(), close_bot_session=False
            )
        finally:
            # A profile still waiting for Telegram is not worth waiting for: the next start
            # sets whatever it did not.
            profile.cancel()
            try:
                # Let the current tick, the refresh pass in flight and the crawl request finish
                # their writes; cancel only if they hang.
                scheduler.stop()
                if crawler is not None:
                    crawler.stop()
                await asyncio.wait_for(asyncio.gather(*background), SHUTDOWN_GRACE)
            except TimeoutError:
                log.warning("background tasks did not stop in %d s, cancelled", SHUTDOWN_GRACE)
            except Exception:
                log.exception("a background task ended with an error")
            finally:
                # The profile's request in flight ends before the session it uses is closed.
                # wait() does not raise the profile's cancellation, nor swallow one of main().
                await asyncio.wait({profile})
                await bot.session.close()
                await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
