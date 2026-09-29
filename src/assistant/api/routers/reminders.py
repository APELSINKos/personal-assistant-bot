"""Reminders: upcoming list, create from the user's local time, cancel."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import ReminderIn, ReminderOut
from assistant.api.views import reminder_out
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.services import reminders

router = APIRouter(tags=["reminders"])


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(
    user: CurrentUser,
    db: Session,
    status: Literal["pending"] = "pending",
) -> list[ReminderOut]:
    return [reminder_out(r, user.timezone) for r in await reminders.pending(db, user.id)]


@router.post("/reminders", response_model=ReminderOut, status_code=201)
async def create_reminder(
    body: ReminderIn,
    user: CurrentUser,
    db: Session,
    state: State,
) -> ReminderOut:
    try:
        when = datetime.strptime(body.due_local, "%Y-%m-%dT%H:%M")
    except ValueError as error:  # e.g. 30 February passes the pattern but is not a date
        raise InvalidInput(field="due_local", reason="format") from error
    reminder = await reminders.create(db, user, body.text, when, state.clock())
    await db.commit()
    return reminder_out(reminder, user.timezone)


@router.delete("/reminders/{reminder_id}", status_code=204)
async def cancel_reminder(reminder_id: int, user: CurrentUser, db: Session) -> Response:
    if not await reminders.cancel(db, user.id, reminder_id):
        raise NotFound(entity="reminder")
    await db.commit()
    return Response(status_code=204)
