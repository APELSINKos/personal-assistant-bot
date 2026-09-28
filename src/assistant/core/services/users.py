"""User lifecycle and personal settings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS, get_settings
from assistant.core.errors import InvalidInput
from assistant.core.i18n import SUPPORTED
from assistant.core.models import User
from assistant.core.services import reminders
from assistant.core.timeutil import is_valid_timezone, parse_hhmm, utcnow


async def get(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def ensure(
    session: AsyncSession,
    user_id: int,
    first_name: str | None,
    tg_language: str | None,
    now: datetime | None = None,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        settings = get_settings()
        user = User(
            id=user_id,
            first_name=first_name,
            tg_language=tg_language,
            language=None,
            city=settings.default_city,
            lat=settings.default_lat,
            lon=settings.default_lon,
            timezone=settings.default_timezone,
            morning_enabled=True,
            morning_time=settings.default_morning_time,
            bot_blocked=False,
        )
        session.add(user)
    else:
        if user.first_name != first_name:
            user.first_name = first_name
        if user.tg_language != tg_language:
            user.tg_language = tg_language
        if user.bot_blocked:
            user.bot_blocked = False
            await reminders.expire_stale(session, user.id, now or utcnow())
    await session.flush()
    return user


async def set_language(session: AsyncSession, user: User, lang: str | None) -> None:
    if lang is not None and lang not in SUPPORTED:
        raise InvalidInput(field="language", reason="unsupported")
    user.language = lang
    await session.flush()


async def set_city(
    session: AsyncSession,
    user: User,
    name: str,
    lat: float,
    lon: float,
    timezone: str,
) -> None:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= LIMITS.city_length * 2 or not is_valid_timezone(timezone):
        raise InvalidInput(field="city", reason="invalid")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidInput(field="city", reason="invalid")
    user.city, user.lat, user.lon, user.timezone = cleaned, lat, lon, timezone
    await session.flush()


async def set_morning(
    session: AsyncSession,
    user: User,
    *,
    enabled: bool | None = None,
    time: str | None = None,
) -> None:
    if time is not None:
        parsed = parse_hhmm(time)
        if parsed is None:
            raise InvalidInput(field="time", reason="format")
        user.morning_time = parsed
    if enabled is not None:
        user.morning_enabled = enabled
    await session.flush()


async def mark_blocked(session: AsyncSession, user_id: int) -> None:
    await session.execute(update(User).where(User.id == user_id).values(bot_blocked=True))
