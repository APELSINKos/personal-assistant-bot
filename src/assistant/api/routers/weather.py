"""The forecast of a city, and its week as a picture — shared from the app or sent to the bot
chat."""

from __future__ import annotations

from typing import Annotated

from aiogram import Bot
from fastapi import APIRouter, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api import share_flow
from assistant.api.deps import CurrentUser, Session, State
from assistant.api.errors import RateLimited
from assistant.api.schemas import ForecastCityOut, ForecastOut, SharedOut
from assistant.api.state import AppState
from assistant.api.views import forecast_out, user_translator
from assistant.core.errors import UpstreamUnavailable
from assistant.core.i18n import Translator
from assistant.core.models import User
from assistant.core.services import cities, forecast_cards, weather
from assistant.core.services.forecast_cards import ForecastCard

router = APIRouter(tags=["weather"])

# The home city (0) or one of the extra cities; SQLite keeps signed 64-bit ids.
CityId = Annotated[int, Query(ge=0, le=2**63 - 1)]


async def _place(db: AsyncSession, user: User, city: int) -> tuple[ForecastCityOut, float, float]:
    """The city shown, with its coordinates: the home one for 0, else one of the user's extra
    cities — a foreign or deleted one is 404."""
    if city:
        place = await cities.get(db, user.id, city)
        return ForecastCityOut(id=place.id, name=place.name, home=False), place.lat, place.lon
    return ForecastCityOut(id=0, name=user.city, home=True), user.lat, user.lon


@router.get("/weather", response_model=ForecastOut)
async def get_weather(
    user: CurrentUser, db: Session, state: State, city: CityId = 0
) -> ForecastOut:
    """The forecast of the home city (city 0) or of one of the extra cities, each on its own
    clock."""
    shown, lat, lon = await _place(db, user, city)
    found = await weather.forecast(state.meteo, shown.name, lat, lon, user_id=user.id)
    return forecast_out(found, shown, state.clock(), user_translator(user))


async def _draw(
    db: AsyncSession, user: User, city: int, state: AppState, bot: Bot
) -> tuple[ForecastCard, bytes, Translator]:
    """The picture of the city's week, within the user's budget of pictures a minute: a refused
    one asks Open-Meteo nothing."""
    shown, lat, lon = await _place(db, user, city)
    wait = state.cards.check(user.id)
    if wait is not None:
        raise RateLimited(wait)
    found = await weather.forecast(state.meteo, shown.name, lat, lon, user_id=user.id)
    name = await share_flow.bot_name(bot)
    card = forecast_cards.card_for(found, state.clock(), name)
    if card is None:  # not a day from the place's today on: the week is not there
        raise UpstreamUnavailable(service="open-meteo")
    t = user_translator(user)
    return card, await forecast_cards.draw_card(card, t), t


@router.post("/weather/share", response_model=SharedOut)
async def share_forecast(
    user: CurrentUser, db: Session, state: State, city: CityId = 0
) -> SharedOut:
    """The week as a picture in a message prepared for Telegram.WebApp.shareMessage."""
    bot = share_flow.bot_of(state)
    site = share_flow.site_of(state)
    card, image, t = await _draw(db, user, city, state, bot)
    caption = forecast_cards.caption(card, t)
    return await share_flow.prepare(db, bot, site, user.id, image, caption, state.clock())


@router.post("/weather/card", status_code=204)
async def send_forecast(user: CurrentUser, db: Session, state: State, city: CityId = 0) -> Response:
    """The week as a photo in the chat with the bot, to forward from there."""
    bot = share_flow.bot_of(state)
    card, image, t = await _draw(db, user, city, state, bot)
    await share_flow.send(bot, user.id, image, "forecast.jpg", forecast_cards.caption(card, t))
    return Response(status_code=204)
