"""Reminders: list, create (one-off or repeat), edit, parse a phrase, snooze, done, cancel."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Response

from assistant.api.deps import CurrentUser, ItemId, Session, State
from assistant.api.schemas import (
    ParseIn,
    ParseOut,
    ReminderIn,
    ReminderOut,
    ReminderPatch,
    RuleIn,
    SnoozeIn,
)
from assistant.api.views import reminder_out, user_translator
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import Repeat
from assistant.core.services import phrases, reminders
from assistant.core.services.recurrence import Rule, describe
from assistant.core.timeutil import local_today, to_local

router = APIRouter(tags=["reminders"])
_MIN_YEAR, _MAX_YEAR = 2000, 2100


def _wall(due_local: str) -> datetime:
    try:
        return datetime.strptime(due_local, "%Y-%m-%dT%H:%M")
    except ValueError as error:  # e.g. 30 February passes the pattern but is not a date
        raise InvalidInput(field="due_local", reason="format") from error


def _rule(body: RuleIn, today: date) -> Rule:
    anchor = body.anchor_date or today
    if not _MIN_YEAR <= anchor.year <= _MAX_YEAR:
        raise InvalidInput(field="rule", reason="repeat_invalid")
    repeat = Repeat(body.repeat)
    return Rule(
        repeat=repeat,
        time_local=body.time_local,
        anchor_date=anchor,
        # Only the fields the chosen kind actually uses are stored; the rest are noise.
        weekdays=body.weekdays if repeat is Repeat.WEEKLY else None,
        interval_weeks=body.interval_weeks if repeat is Repeat.WEEKLY else 1,
        month_day=body.month_day if repeat is Repeat.MONTHLY else None,
    )


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(
    user: CurrentUser,
    db: Session,
    status: Literal["pending"] = "pending",
) -> list[ReminderOut]:
    t = user_translator(user)
    return [reminder_out(r, user.timezone, t) for r in await reminders.pending(db, user.id)]


@router.post("/reminders", response_model=ReminderOut, status_code=201)
async def create_reminder(
    body: ReminderIn, user: CurrentUser, db: Session, state: State
) -> ReminderOut:
    if (body.due_local is None) == (body.rule is None):
        raise InvalidInput(field="due_local", reason="schedule")
    now = state.clock()
    if body.rule is not None:
        rule = _rule(body.rule, local_today(user.timezone, now))
        reminder = await reminders.create_repeating(db, user, body.text, rule, now)
    else:
        assert body.due_local is not None
        reminder = await reminders.create(db, user, body.text, _wall(body.due_local), now)
    await db.commit()
    return reminder_out(reminder, user.timezone, user_translator(user))


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
async def patch_reminder(
    reminder_id: ItemId, body: ReminderPatch, user: CurrentUser, db: Session, state: State
) -> ReminderOut:
    if body.due_local is not None and body.rule is not None:
        raise InvalidInput(field="due_local", reason="schedule")
    now = state.clock()
    reminder = await reminders.update_reminder(
        db,
        user,
        reminder_id,
        text=body.text,
        when_local=_wall(body.due_local) if body.due_local else None,
        rule=_rule(body.rule, local_today(user.timezone, now)) if body.rule else None,
        now=now,
    )
    await db.commit()
    return reminder_out(reminder, user.timezone, user_translator(user))


@router.post("/reminders/parse", response_model=ParseOut)
async def parse_reminder(body: ParseIn, user: CurrentUser, state: State) -> ParseOut:
    local_now = to_local(state.clock(), user.timezone)
    parsed = phrases.parse(body.text, local_now)
    if parsed is None:
        raise InvalidInput(field="text", reason="phrase_not_understood")
    reminders.clean_text(parsed.text)
    rule = parsed.rule(local_now)
    when = parsed.when(local_now)
    if when is None and parsed.repeat is Repeat.NONE:
        # No time yet: still tell the form which day was meant.
        when = parsed.with_time("12:00").when(local_now)
    return ParseOut(
        text=parsed.text,
        repeat=parsed.repeat.value,
        date=when.date() if when else None,
        time=parsed.time if parsed.delta is None else (when.strftime("%H:%M") if when else None),
        weekdays=parsed.weekdays,
        interval_weeks=parsed.interval_weeks,
        month_day=parsed.month_day,
        description=describe(rule, user_translator(user)) if rule else None,
    )


@router.post("/reminders/{reminder_id}/snooze", response_model=ReminderOut)
async def snooze_reminder(
    reminder_id: ItemId, body: SnoozeIn, user: CurrentUser, db: Session, state: State
) -> ReminderOut:
    reminder = await reminders.get_owned(db, user.id, reminder_id)
    if reminder is None:
        raise NotFound(entity="reminder")
    now = state.clock()
    # A firing already due (or overdue) never gets "snoozed" into the past: count from
    # whichever is later, the real clock or the reminder's own due moment.
    base = max(now, reminder.due_at)
    until = reminders.snooze_until(body.kind, reminder.due_at, user.timezone, base)
    result = await reminders.snooze(db, user, reminder_id, until, now)
    await db.commit()
    return reminder_out(result, user.timezone, user_translator(user))


@router.post("/reminders/{reminder_id}/done", status_code=204)
async def done_reminder(reminder_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await reminders.done(db, user.id, reminder_id):
        raise NotFound(entity="reminder")
    await db.commit()
    return Response(status_code=204)


@router.delete("/reminders/{reminder_id}", status_code=204)
async def cancel_reminder(reminder_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await reminders.cancel(db, user.id, reminder_id):
        raise NotFound(entity="reminder")
    await db.commit()
    return Response(status_code=204)
