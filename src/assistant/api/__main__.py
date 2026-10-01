"""Entry point: python -m assistant.api — one uvicorn worker on 127.0.0.1."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import uvicorn

from assistant.api.app import create_app
from assistant.api.routers.health import read_commit
from assistant.core.clients.calendars import CalendarFetcher
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import get_settings
from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import check_translations
from assistant.core.logging import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[3]
# Open-Meteo and the Bank of Russia get a shorter budget here than in the bot: a screen of
# the app waits for them, and a quick 503 beats a skeleton that hangs for ten seconds.
UPSTREAM_TIMEOUT = 4.0


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, [settings.bot_token.get_secret_value()])
    check_translations()
    engine = create_engine(settings.database_url)
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as http:
            app = create_app(
                settings=settings,
                sessionmaker=make_sessionmaker(engine),
                meteo=OpenMeteoClient(http),
                cbr=CbrClient(http),
                calendars=CalendarFetcher(http),
                commit=read_commit(REPO_ROOT),
            )
            config = uvicorn.Config(
                app,
                host=settings.api_host,
                port=settings.api_port,
                log_config=None,
                access_log=False,
                proxy_headers=True,
                forwarded_allow_ips="127.0.0.1",
                server_header=False,
            )
            await uvicorn.Server(config).serve()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
