"""The class schedule: its source, the MIREA group search, connecting, refreshing, alerts.

A user's changes run one at a time (AppState.schedule_lock), and each reads the source only
once it is its turn: a second click on «refresh» finds the limit used up, and a connect waits
for a refresh in progress instead of being overwritten by the older calendar. Every download
or parse a user starts counts against their budget (schedule.attempt_limiter) before it."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from starlette.requests import ClientDisconnect

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.errors import RateLimited
from assistant.api.schemas import GroupOut, GroupsOut, ScheduleIn, SchedulePatch, ScheduleState
from assistant.api.state import AppState
from assistant.api.views import schedule_out
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import User
from assistant.core.services import groups, schedule
from assistant.core.services.group_names import MIREA_ZONE
from assistant.core.timeutil import local_today

log = logging.getLogger(__name__)
router = APIRouter(tags=["schedule"])
NAME_LENGTH = 255  # the longest file name common systems allow; the title keeps 100 of it


async def _state(db: Session, user: User, now: datetime) -> ScheduleState:
    source = await schedule.get_source(db, user.id)
    if source is None:
        return ScheduleState(source=None)
    ahead = await schedule.lessons_ahead(db, user.id, now)
    return ScheduleState(source=schedule_out(source, now, ahead))


def _attempt(state: AppState, user: User) -> None:
    """Count a download or parse the user starts; past their budget, 429 before any of it."""
    wait = state.attempts.check(user.id)
    if wait is not None:
        raise RateLimited(wait)


@router.get("/schedule", response_model=ScheduleState)
async def get_schedule(user: CurrentUser, db: Session, state: State) -> ScheduleState:
    return await _state(db, user, state.clock())


@router.get("/schedule/groups", response_model=GroupsOut)
async def search_groups(
    user: CurrentUser, db: Session, state: State, q: Annotated[str, Query(max_length=40)] = ""
) -> GroupsOut:
    # Whether a semester is still on goes by the app's clock, like every other date here.
    found = await groups.search(db, q, today=local_today(MIREA_ZONE, state.clock()))
    return GroupsOut(
        groups=[GroupOut(id=group.id, name=group.name) for group in found],
        building=await groups.building(db),
    )


@router.put("/schedule", response_model=ScheduleState)
async def connect(body: ScheduleIn, user: CurrentUser, db: Session, state: State) -> ScheduleState:
    if (body.mirea_id is None) == (body.url is None):
        raise InvalidInput(field="schedule", reason="source")  # exactly one of the two
    await schedule.precheck(db, mirea_id=body.mirea_id, url=body.url)
    _attempt(state, user)
    async with state.schedule_lock(user.id):
        now = state.clock()
        if body.mirea_id is not None:
            await schedule.connect_mirea(db, user, body.mirea_id, state.calendars, now)
        else:
            await schedule.connect_url(db, user, body.url or "", state.calendars, now)
        await db.commit()
        return await _state(db, user, now)


def _declared_size(request: Request) -> int:
    """The body's size as the client announced it; 0 when it did not say (or not readably)."""
    try:
        return int(request.headers.get("content-length", "0"))
    except ValueError:
        return 0


async def _receive(request: Request) -> bytes:
    """The streamed body, refused as soon as it runs past FILE_LIMIT."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > schedule.FILE_LIMIT:
            raise InvalidInput(field="file", reason="too_large")
    return bytes(body)


@router.post("/schedule/file", response_model=ScheduleState)
async def upload(
    request: Request,
    user: CurrentUser,
    db: Session,
    state: State,
    name: Annotated[str | None, Query(max_length=NAME_LENGTH)] = None,
) -> ScheduleState | Response:
    """The calendar is the raw request body (the app sends the picked file as it is)."""
    if _declared_size(request) > schedule.FILE_LIMIT:
        raise InvalidInput(field="file", reason="too_large")  # no need to receive it first
    _attempt(state, user)
    async with state.schedule_lock(user.id):
        # Received only once it is its turn: uploads waiting for the lock hold no body.
        try:
            body = await _receive(request)
        except ClientDisconnect:
            # The app was closed or lost the network mid-upload; the server drops any answer.
            log.info("schedule upload of user %s broke off", user.id)
            return Response(status_code=400)
        now = state.clock()
        await schedule.connect_file(db, user, body, name, now)
        await db.commit()
        return await _state(db, user, now)


@router.post("/schedule/refresh", response_model=ScheduleState)
async def refresh(user: CurrentUser, db: Session, state: State) -> ScheduleState:
    async with state.schedule_lock(user.id):
        source = await schedule.get_source(db, user.id)
        if source is None:
            raise NotFound(entity="schedule")
        now = state.clock()
        wait = schedule.refresh_wait(source, now)
        if wait > 0:
            raise RateLimited(wait)
        _attempt(state, user)
        await schedule.refresh(db, user, state.calendars, now)
        await db.commit()
        return await _state(db, user, now)


@router.patch("/schedule", response_model=ScheduleState)
async def patch_schedule(
    body: SchedulePatch, user: CurrentUser, db: Session, state: State
) -> ScheduleState:
    async with state.schedule_lock(user.id):
        await schedule.set_alert_minutes(db, user.id, body.lesson_reminder_minutes)
        await db.commit()
        return await _state(db, user, state.clock())


@router.delete("/schedule", status_code=204)
async def disconnect(user: CurrentUser, db: Session, state: State) -> Response:
    async with state.schedule_lock(user.id):
        if not await schedule.disconnect(db, user.id):
            raise NotFound(entity="schedule")
        await db.commit()
    return Response(status_code=204)
