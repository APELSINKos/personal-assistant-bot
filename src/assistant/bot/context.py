"""Everything a handler needs, injected by the UserContext middleware as `ctx`."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.config import Settings
from assistant.core.i18n import Translator
from assistant.core.models import User
from assistant.core.ratelimit import RateLimiter


@dataclass
class Ctx:
    session: AsyncSession
    user: User
    t: Translator
    state: FSMContext
    meteo: OpenMeteoClient
    cbr: CbrClient
    calendars: Calendars
    attempts: RateLimiter  # schedule.attempt_limiter: the downloads and parses users start
    settings: Settings

    @property
    def lang(self) -> str:
        return self.t.lang
