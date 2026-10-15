"""Shared pictures: the ones Telegram downloads by token when a user shares a habit's card or the
week's forecast from the Mini App.

Sharing from the Mini App goes through a prepared inline message whose photo is a link, so the
picture must stay reachable without the user's signature until that message can no longer be
sent. The link carries a 256-bit token; a user keeps only their newest few pictures of both kinds.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.models import ShareCard

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32)
KEEP_LONGEST = timedelta(days=7)
KEEP_AFTER_EXPIRY = timedelta(hours=1)
PER_USER = 10


def is_token(value: str) -> bool:
    return TOKEN.fullmatch(value) is not None


async def save(
    session: AsyncSession, user_id: int, image: bytes, now: datetime, *, habit_id: int | None = None
) -> str:
    """Store a picture for the longest time allowed; `keep_until` shortens it once Telegram says
    when the prepared message expires. A habit's card names its habit and goes with it; the
    forecast names none. The user's older pictures beyond PER_USER go."""
    token = secrets.token_urlsafe(32)
    session.add(
        ShareCard(
            token=token,
            user_id=user_id,
            habit_id=habit_id,
            image=image,
            created_at=now,
            expires_at=now + KEEP_LONGEST,
        )
    )
    await session.flush()
    stale = (
        select(ShareCard.token)
        .where(ShareCard.user_id == user_id)
        .order_by(ShareCard.created_at.desc(), ShareCard.token)
        .offset(PER_USER)
    )
    await session.execute(delete(ShareCard).where(ShareCard.token.in_(stale)))
    return token


async def keep_until(session: AsyncSession, token: str, expires: datetime, now: datetime) -> None:
    card = await session.get(ShareCard, token)
    if card is not None:
        card.expires_at = min(expires + KEEP_AFTER_EXPIRY, now + KEEP_LONGEST)
        await session.flush()


async def image(session: AsyncSession, token: str, now: datetime) -> bytes | None:
    if not is_token(token):
        return None
    card = await session.get(ShareCard, token)
    return card.image if card is not None and card.expires_at > now else None


async def forget(session: AsyncSession, token: str) -> None:
    await session.execute(delete(ShareCard).where(ShareCard.token == token))


async def prune(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(ShareCard).where(ShareCard.expires_at <= now))
    return int(result.rowcount)  # type: ignore[attr-defined]
