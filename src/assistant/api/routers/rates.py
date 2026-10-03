"""The Bank of Russia's rates: every currency of the day and one currency over 30 days (the
day's USD and EUR alone stay at /rates, in routers/today)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.deps import CurrentUser, State
from assistant.api.schemas import RateHistoryOut, RatesAllOut
from assistant.api.views import history_out, rates_all_out
from assistant.core.errors import NotFound

router = APIRouter(tags=["rates"])
HISTORY_DAYS = 30  # fixed: every other length would be another request to the bank


@router.get("/rates/all", response_model=RatesAllOut)
async def all_rates(user: CurrentUser, state: State) -> RatesAllOut:
    return rates_all_out(await state.cbr.daily(), user)


@router.get("/rates/history", response_model=RateHistoryOut)
async def rate_history(
    user: CurrentUser, state: State, code: Annotated[str, Query(pattern=r"^[A-Z]{3}$")]
) -> RateHistoryOut:
    try:
        points = await state.cbr.history(code, HISTORY_DAYS)
    except LookupError as error:
        raise NotFound(entity="currency") from error
    return history_out(code, points)
