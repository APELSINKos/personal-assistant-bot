"""Money: the month with its totals, categories and entries, one entry for its form; entries,
categories and the total budget changed. Amounts go in as decimals («430.50») and come out in
hundredths."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api.deps import CurrentUser, ItemId, Session, State
from assistant.api.schemas import (
    BudgetIn,
    MeOut,
    MoneyCategoryIn,
    MoneyCategoryOut,
    MoneyCategoryPatch,
    MoneyEntryIn,
    MoneyEntryOut,
    MoneyEntryPatch,
    MoneyEntrySaved,
    MoneyMonthOut,
)
from assistant.api.views import (
    alert_out,
    category_out,
    entry_out,
    hundredths,
    me_out,
    month_out,
    user_translator,
)
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import MoneyEntry, User
from assistant.core.services import money, money_month
from assistant.core.services.money import KEEP
from assistant.core.timeutil import local_today

router = APIRouter(tags=["money"])
MonthParam = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]


def _first(value: str | None, today: date) -> date:
    if value is None:
        return today.replace(day=1)
    try:
        return datetime.strptime(value, "%Y-%m").date()
    except ValueError as error:
        raise InvalidInput(field="month", reason="format") from error


@router.get("/money", response_model=MoneyMonthOut)
async def get_month(
    user: CurrentUser, db: Session, state: State, month: MonthParam = None
) -> MoneyMonthOut:
    now = state.clock()
    first = _first(month, local_today(user.timezone, now))
    data = await money_month.month(db, user, first, now)
    categories = await money.categories(db, user)
    rows = await money_month.entries(db, user, data.first)
    oldest = await money_month.first_month(db, user)
    await db.commit()  # the presets of a first visit
    return month_out(
        data,
        oldest,
        categories,
        [entry for entry, _ in rows],
        user,
        user_translator(user),
    )


async def _saved(db: AsyncSession, user: User, entry: MoneyEntry, now: datetime) -> MoneyEntrySaved:
    alerts = await money_month.alerts_after(db, user, entry, now)
    await db.commit()
    t = user_translator(user)
    return MoneyEntrySaved(entry=entry_out(entry), alerts=[alert_out(item, t) for item in alerts])


@router.post("/money/entries", response_model=MoneyEntrySaved, status_code=201)
async def add_entry(
    body: MoneyEntryIn, user: CurrentUser, db: Session, state: State
) -> MoneyEntrySaved:
    now = state.clock()
    entry = await money.add_entry(
        db,
        user,
        amount=hundredths(body.amount),
        category_id=body.category_id,
        note=body.note,
        day=body.day,
        now=now,
    )
    return await _saved(db, user, entry, now)


@router.get("/money/entries/{entry_id}", response_model=MoneyEntryOut)
async def get_entry(entry_id: ItemId, user: CurrentUser, db: Session) -> MoneyEntryOut:
    return entry_out(await money.entry(db, user, entry_id))


@router.patch("/money/entries/{entry_id}", response_model=MoneyEntrySaved)
async def change_entry(
    entry_id: ItemId, body: MoneyEntryPatch, user: CurrentUser, db: Session, state: State
) -> MoneyEntrySaved:
    now = state.clock()
    entry = await money.update_entry(
        db,
        user,
        entry_id,
        amount=None if body.amount is None else hundredths(body.amount),
        category_id=body.category_id,
        note=body.note,
        day=body.day,
        now=now,
    )
    return await _saved(db, user, entry, now)


@router.delete("/money/entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await money.delete_entry(db, user, entry_id):
        raise NotFound(entity="entry")
    await db.commit()
    return Response(status_code=204)


@router.get("/money/categories", response_model=list[MoneyCategoryOut])
async def list_categories(user: CurrentUser, db: Session) -> list[MoneyCategoryOut]:
    found = await money.categories(db, user)
    await db.commit()
    t = user_translator(user)
    return [category_out(item, t) for item in found]


@router.post("/money/categories", response_model=MoneyCategoryOut, status_code=201)
async def create_category(
    body: MoneyCategoryIn, user: CurrentUser, db: Session
) -> MoneyCategoryOut:
    created = await money.create_category(db, user, body.kind, body.name, body.emoji)
    await db.commit()
    return category_out(created, user_translator(user))


@router.patch("/money/categories/{category_id}", response_model=MoneyCategoryOut)
async def change_category(
    category_id: ItemId, body: MoneyCategoryPatch, user: CurrentUser, db: Session
) -> MoneyCategoryOut:
    budget: object = KEEP
    if "budget" in body.model_fields_set:
        budget = None if body.budget is None else hundredths(body.budget)
    changed = await money.update_category(
        db, user, category_id, name=body.name, emoji=body.emoji, hidden=body.hidden, budget=budget
    )
    await db.commit()
    return category_out(changed, user_translator(user))


@router.put("/money/budget", response_model=MeOut)
async def put_budget(body: BudgetIn, user: CurrentUser, db: Session) -> MeOut:
    await money.set_budget(db, user, None if body.amount is None else hundredths(body.amount))
    await db.commit()
    return me_out(user)
