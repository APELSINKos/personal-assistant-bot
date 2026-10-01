"""The class schedule: its source, the MIREA group search, connecting, refreshing, alerts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.errors import RateLimited
from assistant.api.schemas import GroupOut, GroupsOut, ScheduleIn, SchedulePatch, ScheduleState
from assistant.api.views import schedule_out
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import User
from assistant.core.services import groups, schedule

router = APIRouter(tags=["schedule"])


async def _state(db: Session, user: User, now: datetime) -> ScheduleState:
    source = await schedule.get_source(db, user.id)
    if source is None:
        return ScheduleState(source=None)
    ahead = await schedule.lessons_ahead(db, user.id, now)
    return ScheduleState(source=schedule_out(source, now, ahead))


@router.get("/schedule", response_model=ScheduleState)
async def get_schedule(user: CurrentUser, db: Session, state: State) -> ScheduleState:
    return await _state(db, user, state.clock())


@router.get("/schedule/groups", response_model=GroupsOut)
async def search_groups(
    user: CurrentUser, db: Session, q: Annotated[str, Query(max_length=40)] = ""
) -> GroupsOut:
    found = await groups.search(db, q)
    return GroupsOut(
        groups=[GroupOut(id=group.id, name=group.name) for group in found],
        building=await groups.building(db),
    )


@router.put("/schedule", response_model=ScheduleState)
async def connect(body: ScheduleIn, user: CurrentUser, db: Session, state: State) -> ScheduleState:
    if (body.mirea_id is None) == (body.url is None):
        raise InvalidInput(field="schedule", reason="source")  # exactly one of the two
    now = state.clock()
    if body.mirea_id is not None:
        await schedule.connect_mirea(db, user, body.mirea_id, state.calendars, now)
    else:
        await schedule.connect_url(db, user, body.url or "", state.calendars, now)
    await db.commit()
    return await _state(db, user, now)


@router.post("/schedule/file", response_model=ScheduleState)
async def upload(
    request: Request,
    user: CurrentUser,
    db: Session,
    state: State,
    name: Annotated[str | None, Query(max_length=100)] = None,
) -> ScheduleState:
    """The calendar is the raw request body (the app sends the picked file as it is)."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > schedule.FILE_LIMIT:
            raise InvalidInput(field="file", reason="too_large")
    now = state.clock()
    await schedule.connect_file(db, user, bytes(body), name, now)
    await db.commit()
    return await _state(db, user, now)


@router.post("/schedule/refresh", response_model=ScheduleState)
async def refresh(user: CurrentUser, db: Session, state: State) -> ScheduleState:
    source = await schedule.get_source(db, user.id)
    if source is None:
        raise NotFound(entity="schedule")
    now = state.clock()
    wait = schedule.refresh_wait(source, now)
    if wait > 0:
        raise RateLimited(wait)
    await schedule.refresh(db, user, state.calendars, now)
    await db.commit()
    return await _state(db, user, now)


@router.patch("/schedule", response_model=ScheduleState)
async def patch_schedule(
    body: SchedulePatch, user: CurrentUser, db: Session, state: State
) -> ScheduleState:
    await schedule.set_alert_minutes(db, user.id, body.lesson_reminder_minutes)
    await db.commit()
    return await _state(db, user, state.clock())


@router.delete("/schedule", status_code=204)
async def disconnect(user: CurrentUser, db: Session) -> Response:
    if not await schedule.disconnect(db, user.id):
        raise NotFound(entity="schedule")
    await db.commit()
    return Response(status_code=204)
