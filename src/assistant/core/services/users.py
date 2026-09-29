"""User lifecycle and personal settings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
    *,
    from_bot: bool = True,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        # A new user's first requests (or bot updates) arrive together and all find no row;
        # the ones that lose the race must not fail on the primary key, so skip duplicates.
        settings = get_settings()
        await session.execute(
            sqlite_insert(User)
            .values(
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
                can_write=from_bot,
            )
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        # Load the row as stored (ours or the winner's), never an object kept in the session.
        user = await session.get_one(User, user_id, populate_existing=True)
    if user.first_name != first_name:
        user.first_name = first_name
    # Telegram does not always send a language code; keep the last known one then.
    if tg_language is not None and user.tg_language != tg_language:
        user.tg_language = tg_language
    # Only a message to the bot proves the bot may write here and that it is unblocked;
    # opening the app does neither.
    if from_bot:
        if not user.can_write:
            user.can_write = True
        if user.bot_blocked:
            user.bot_blocked = False
            await reminders.expire_stale(session, user.id, now or utcnow(), user.timezone)
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
    now: datetime | None = None,
) -> None:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= LIMITS.city_length * 2 or not is_valid_timezone(timezone):
        raise InvalidInput(field="city", reason="invalid")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidInput(field="city", reason="invalid")
    user.city, user.lat, user.lon, user.timezone = cleaned, lat, lon, timezone
    await reminders.reschedule_repeating(session, user, now)
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


async def allow_write(session: AsyncSession, user: User) -> None:
    user.can_write = True
    await session.flush()
