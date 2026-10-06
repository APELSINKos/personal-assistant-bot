"""«Сегодня», the forecast of a city and exchange rates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import ForecastCityOut, ForecastOut, RatesOut, TodayOut
from assistant.api.views import forecast_out, rates_out, today_out, user_translator
from assistant.core.services import cities, digest, weather

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayOut)
async def get_today(user: CurrentUser, db: Session, state: State) -> TodayOut:
    data = await digest.today(db, user, state.meteo, state.cbr, state.clock())
    return today_out(data, user.timezone, user_translator(user))


@router.get("/weather", response_model=ForecastOut)
async def get_weather(
    user: CurrentUser,
    db: Session,
    state: State,
    city: Annotated[int, Query(ge=0, le=2**63 - 1)] = 0,
) -> ForecastOut:
    """The forecast of the home city (city 0) or of one of the extra cities, each on its own
    clock."""
    if city:
        place = await cities.get(db, user.id, city)
        shown = ForecastCityOut(id=place.id, name=place.name, home=False)
        lat, lon = place.lat, place.lon
    else:
        shown = ForecastCityOut(id=0, name=user.city, home=True)
        lat, lon = user.lat, user.lon
    found = await weather.forecast(state.meteo, shown.name, lat, lon)
    return forecast_out(found, shown, state.clock(), user_translator(user))


@router.get("/rates", response_model=RatesOut)
async def get_rates(user: CurrentUser, state: State) -> RatesOut:
    return rates_out(await state.cbr.daily())
