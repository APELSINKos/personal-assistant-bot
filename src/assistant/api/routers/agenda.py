"""The calendar: every day of a range with its reminders, in the user's city zone."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.deps import CurrentUser, Session
from assistant.api.schemas import AgendaDayOut, AgendaItemOut, AgendaOut
from assistant.api.views import user_translator
from assistant.core.errors import InvalidInput
from assistant.core.services import reminders
from assistant.core.services.recurrence import describe
from assistant.core.timeutil import local_to_utc, to_local

router = APIRouter(tags=["agenda"])
MAX_DAYS = 62


@router.get("/agenda", response_model=AgendaOut)
async def agenda(
    user: CurrentUser,
    db: Session,
    start_day: Annotated[date, Query(alias="from")],
    end_day: Annotated[date, Query(alias="to")],
) -> AgendaOut:
    if end_day < start_day or (end_day - start_day).days >= MAX_DAYS:
        raise InvalidInput(field="to", reason="range")
    tz = user.timezone
    start = local_to_utc(datetime.combine(start_day, time()), tz)
    end = local_to_utc(datetime.combine(end_day + timedelta(days=1), time()), tz)
    t = user_translator(user)
    days: dict[date, list[AgendaItemOut]] = {
        start_day + timedelta(days=i): [] for i in range((end_day - start_day).days + 1)
    }
    for reminder, moment in await reminders.between(db, user, start, end):
        local = to_local(moment, tz)
        rule = reminders.rule_of(reminder)
        days.setdefault(local.date(), []).append(
            AgendaItemOut(
                kind="reminder",
                id=reminder.id,
                time=local.strftime("%H:%M"),
                text=reminder.text,
                repeat=reminder.repeat.value,
                description=describe(rule, t) if rule else None,
            )
        )
    return AgendaOut(days=[AgendaDayOut(date=day, items=items) for day, items in days.items()])
