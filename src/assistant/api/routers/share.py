"""Shared cards: the one path without the user's signature — Telegram downloads the picture of
a prepared message from here by its unguessable token."""

from __future__ import annotations

from fastapi import APIRouter, Response

from assistant.api.deps import Session, State
from assistant.core.errors import NotFound
from assistant.core.services import sharing

router = APIRouter(tags=["share"])


@router.get(
    "/share/{token}.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def shared_card(token: str, db: Session, state: State) -> Response:
    image = await sharing.image(db, token, state.clock())
    if image is None:
        raise NotFound(entity="card")
    return Response(image, media_type="image/jpeg")
