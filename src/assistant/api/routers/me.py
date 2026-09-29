"""The user's profile and settings."""

from __future__ import annotations

from fastapi import APIRouter

from assistant.api.deps import CurrentUser
from assistant.api.schemas import MeOut
from assistant.api.views import me_out

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser) -> MeOut:
    return me_out(user)
