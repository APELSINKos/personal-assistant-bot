"""Everything a request handler needs from the running application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.api.ratelimit import RateLimiter
from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings


@dataclass
class AppState:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    meteo: OpenMeteoClient
    cbr: CbrClient
    calendars: Calendars
    limiter: RateLimiter
    clock: Callable[[], datetime]
    commit: str | None
