"""«Сегодня» and exchange rates."""

from __future__ import annotations

from fastapi import APIRouter

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import RatesOut, TodayOut
from assistant.api.views import rates_out, today_out, user_translator
from assistant.core.services import digest

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayOut)
async def get_today(user: CurrentUser, db: Session, state: State) -> TodayOut:
    data = await digest.today(db, user, state.meteo, state.cbr, state.clock())
    return today_out(data, user_translator(user))


@router.get("/rates", response_model=RatesOut)
async def get_rates(user: CurrentUser, state: State) -> RatesOut:
    return rates_out(await state.cbr.daily())
