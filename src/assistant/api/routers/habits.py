"""Habits: list with statistics, create, delete, mark a day."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response

from assistant.api.deps import CurrentUser, Session, State
from assistant.api.schemas import HabitIn, HabitOut, MarkIn
from assistant.api.views import habit_out
from assistant.core.errors import NotFound
from assistant.core.services import habits

router = APIRouter(tags=["habits"])


@router.get("/habits", response_model=list[HabitOut])
async def list_habits(user: CurrentUser, db: Session, state: State) -> list[HabitOut]:
    return [habit_out(s) for s in await habits.list_with_stats(db, user, state.clock())]


@router.post("/habits", response_model=HabitOut, status_code=201)
async def create_habit(body: HabitIn, user: CurrentUser, db: Session, state: State) -> HabitOut:
    habit = await habits.create(db, user, body.name, state.clock())
    await db.commit()
    return habit_out(await habits.stats_for(db, user, habit.id, state.clock()))


@router.delete("/habits/{habit_id}", status_code=204)
async def delete_habit(habit_id: int, user: CurrentUser, db: Session) -> Response:
    if not await habits.delete(db, user.id, habit_id):
        raise NotFound(entity="habit")
    await db.commit()
    return Response(status_code=204)


@router.put("/habits/{habit_id}/marks/{day}", response_model=HabitOut)
async def mark_day(
    habit_id: int,
    day: date,
    body: MarkIn,
    user: CurrentUser,
    db: Session,
    state: State,
) -> HabitOut:
    stats = await habits.set_mark(db, user, habit_id, day, body.done, state.clock())
    await db.commit()
    return habit_out(stats)
