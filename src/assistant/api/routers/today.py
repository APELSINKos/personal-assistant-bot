"""«Сегодня», current weather and exchange rates."""

from __future__ import annotations

from fastapi import APIRouter

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import RatesOut, TodayOut, WeatherOut
from assistant.api.views import rates_out, today_out, user_translator, weather_out
from assistant.core.services import digest, weather

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayOut)
async def get_today(user: CurrentUser, db: Session, state: State) -> TodayOut:
    data = await digest.today(db, user, state.meteo, state.cbr, state.clock())
    return today_out(data, user_translator(user))


@router.get("/weather", response_model=WeatherOut)
async def get_weather(user: CurrentUser, state: State) -> WeatherOut:
    now = await weather.current(state.meteo, user.city, user.lat, user.lon)
    return weather_out(now, user_translator(user))


@router.get("/rates", response_model=RatesOut)
async def get_rates(user: CurrentUser, state: State) -> RatesOut:
    return rates_out(await state.cbr.daily())
