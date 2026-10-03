"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit

from aiogram import Bot
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant import __version__
from assistant.api import errors
from assistant.api.routers import ALL
from assistant.api.state import AppState
from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings
from assistant.core.ratelimit import RateLimiter
from assistant.core.services import card_kit, schedule
from assistant.core.timeutil import utcnow


def site_origin(url: str | None) -> str | None:
    """«https://host» of the Mini App's address (its path is not kept): the links of shared
    cards point to the same site. None for no address or one that is not HTTPS."""
    parts = urlsplit(url or "")
    return f"https://{parts.netloc}" if parts.scheme == "https" and parts.netloc else None


def create_app(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    meteo: OpenMeteoClient,
    cbr: CbrClient,
    calendars: Calendars,
    commit: str | None = None,
    clock: Callable[[], datetime] = utcnow,
    limiter: RateLimiter | None = None,
    attempts: RateLimiter | None = None,
    card_limiter: RateLimiter | None = None,
    bot: Bot | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Personal Assistant API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.assistant = AppState(
        settings=settings,
        sessionmaker=sessionmaker,
        meteo=meteo,
        cbr=cbr,
        calendars=calendars,
        limiter=limiter or RateLimiter(settings.api_rate_limit),
        attempts=attempts or schedule.attempt_limiter(),
        cards=card_limiter or card_kit.card_limiter(),
        bot=bot,
        site=site_origin(settings.webapp_url),
        clock=clock,
        commit=commit,
    )
    errors.install(app)
    for router in ALL:
        app.include_router(router, prefix="/api")
    return app
