"""Shared cards: the one path without the user's signature — Telegram downloads the picture of
a prepared message from here by its unguessable token."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api.deps import Session, State
from assistant.core.errors import NotFound
from assistant.core.services import sharing

router = APIRouter(tags=["share"])


async def _card(db: AsyncSession, token: str, now: datetime) -> bytes:
    image = await sharing.image(db, token, now)
    if image is None:
        raise NotFound(entity="card")
    return image


@router.get(
    "/share/{token}.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def shared_card(token: str, db: Session, state: State) -> Response:
    return Response(await _card(db, token, state.clock()), media_type="image/jpeg")


@router.head("/share/{token}.jpg", include_in_schema=False)
async def shared_card_head(token: str, db: Session, state: State) -> Response:
    """A link preview may ask for the headers first: the same ones, without the picture."""
    image = await _card(db, token, state.clock())
    return Response(media_type="image/jpeg", headers={"content-length": str(len(image))})
