"""The user's profile and settings, and the city search that feeds them."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import CityIn, CityOut, MeOut, MePatch
from assistant.api.views import me_out, user_language
from assistant.core.services import money, users

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser) -> MeOut:
    return me_out(user)


@router.patch("/me", response_model=MeOut)
async def patch_me(body: MePatch, user: CurrentUser, db: Session) -> MeOut:
    if body.language is not None:
        await users.set_language(db, user, None if body.language == "auto" else body.language)
    if body.morning_enabled is not None or body.morning_time is not None:
        await users.set_morning(db, user, enabled=body.morning_enabled, time=body.morning_time)
    if body.currency is not None:
        await money.set_currency(db, user, body.currency)
    await db.commit()
    return me_out(user)


@router.put("/me/city", response_model=MeOut)
async def put_city(body: CityIn, user: CurrentUser, db: Session) -> MeOut:
    await users.set_city(db, user, body.name, body.lat, body.lon, body.timezone)
    await db.commit()
    return me_out(user)


@router.post("/me/write-access", response_model=MeOut)
async def allow_write(user: CurrentUser, db: Session) -> MeOut:
    """The app got Telegram's permission for the bot to write; Telegram does not re-sign
    initData after that, so the app tells us. A wrong claim only affects this user's own
    deliveries (the bot would get 403 and mark them blocked)."""
    await users.allow_write(db, user)
    await db.commit()
    return me_out(user)


@router.get("/cities", response_model=list[CityOut])
async def search_cities(
    q: Annotated[str, Query(min_length=2, max_length=50)],
    user: CurrentUser,
    state: State,
) -> list[CityOut]:
    found = await state.meteo.search(q.strip(), user_language(user))
    return [CityOut(**asdict(city)) for city in found]
