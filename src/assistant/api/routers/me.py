"""The user's profile and settings, the extra cities of the weather, and the city search that
feeds them."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from assistant.api.deps import CurrentUser, ItemId, Session, State
from assistant.api.schemas import (
    CityIn,
    FoundCityOut,
    MeOut,
    MePatch,
    WeatherCityIn,
    WeatherCityOut,
)
from assistant.api.views import found_city_out, me_out, user_language, weather_city_out
from assistant.core.clients.openmeteo import City
from assistant.core.services import cities, money, users

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
async def put_city(body: CityIn, user: CurrentUser, db: Session, state: State) -> MeOut:
    """A new home city. When it is one of the extra cities, that one leaves the list."""
    await users.set_city(
        db,
        user,
        body.name,
        body.lat,
        body.lon,
        body.timezone,
        now=state.clock(),
        geo_id=body.geo_id,
    )
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


@router.get("/me/cities", response_model=list[WeatherCityOut])
async def list_cities(user: CurrentUser, db: Session) -> list[WeatherCityOut]:
    return [weather_city_out(city) for city in await cities.list_for(db, user.id)]


@router.post("/me/cities", response_model=WeatherCityOut, status_code=201)
async def add_city(body: WeatherCityIn, user: CurrentUser, db: Session) -> WeatherCityOut:
    """An extra city for the weather; the home city and the time of everything stay."""
    added = await cities.add(db, user, City(**body.model_dump()))
    await db.commit()
    return weather_city_out(added)


@router.delete("/me/cities/{city_id}", status_code=204)
async def delete_city(city_id: ItemId, user: CurrentUser, db: Session) -> Response:
    await cities.delete(db, user.id, city_id)
    await db.commit()
    return Response(status_code=204)


@router.get("/cities", response_model=list[FoundCityOut])
async def search_cities(
    q: Annotated[str, Query(min_length=2, max_length=50)],
    user: CurrentUser,
    state: State,
) -> list[FoundCityOut]:
    found = await state.meteo.search(q.strip(), user_language(user), user_id=user.id)
    return [found_city_out(city) for city in found]
