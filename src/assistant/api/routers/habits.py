"""Habits: list with statistics, one habit with its year, create, change, delete, mark a day,
and the share card — shared from the app or sent to the bot chat."""

from __future__ import annotations

from datetime import date

from aiogram import Bot
from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api import share_flow
from assistant.api.deps import CurrentUser, ItemId, Session, State
from assistant.api.errors import RateLimited
from assistant.api.schemas import (
    HabitDetailOut,
    HabitIn,
    HabitOut,
    HabitPatchIn,
    MarkIn,
    SharedOut,
)
from assistant.api.state import AppState
from assistant.api.views import habit_detail_out, habit_out, user_translator
from assistant.core.errors import NotFound
from assistant.core.i18n import Translator
from assistant.core.models import User
from assistant.core.services import cards, habits
from assistant.core.timeutil import local_today

router = APIRouter(tags=["habits"])


@router.get("/habits", response_model=list[HabitOut])
async def list_habits(user: CurrentUser, db: Session, state: State) -> list[HabitOut]:
    return [habit_out(s) for s in await habits.list_with_stats(db, user, state.clock())]


@router.get("/habits/{habit_id}", response_model=HabitDetailOut)
async def get_habit(
    habit_id: ItemId, user: CurrentUser, db: Session, state: State
) -> HabitDetailOut:
    return habit_detail_out(await habits.detail(db, user, habit_id, state.clock()))


@router.post("/habits", response_model=HabitOut, status_code=201)
async def create_habit(body: HabitIn, user: CurrentUser, db: Session, state: State) -> HabitOut:
    look = body.model_dump(exclude={"name"}, exclude_none=True)
    habit = await habits.create(db, user, body.name, state.clock(), **look)
    await db.commit()
    return habit_out(await habits.stats_for(db, user, habit.id, state.clock()))


@router.patch("/habits/{habit_id}", response_model=HabitOut)
async def update_habit(
    habit_id: ItemId, body: HabitPatchIn, user: CurrentUser, db: Session, state: State
) -> HabitOut:
    changes = body.model_dump(exclude_none=True)
    stats = await habits.update(db, user, habit_id, state.clock(), **changes)
    await db.commit()
    return habit_out(stats)


@router.delete("/habits/{habit_id}", status_code=204)
async def delete_habit(habit_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await habits.delete(db, user.id, habit_id):
        raise NotFound(entity="habit")
    await db.commit()
    return Response(status_code=204)


@router.put("/habits/{habit_id}/marks/{day}", response_model=HabitOut)
async def mark_day(
    habit_id: ItemId,
    day: date,
    body: MarkIn,
    user: CurrentUser,
    db: Session,
    state: State,
) -> HabitOut:
    stats = await habits.set_mark(db, user, habit_id, day, body.done, state.clock())
    await db.commit()
    return habit_out(stats)


async def _draw(
    db: AsyncSession, user: User, habit_id: int, state: AppState, bot: Bot
) -> tuple[cards.Card, bytes, Translator]:
    """The user's card for the habit, within their budget of cards a minute."""
    detail = await habits.detail(db, user, habit_id, state.clock())  # a foreign habit: 404
    wait = state.cards.check(user.id)
    if wait is not None:
        raise RateLimited(wait)
    name = await share_flow.bot_name(bot)
    t = user_translator(user)
    card = cards.card_for(detail, local_today(user.timezone, state.clock()), name)
    return card, await cards.draw_card(card, t), t


@router.post("/habits/{habit_id}/share", response_model=SharedOut)
async def share_habit(habit_id: ItemId, user: CurrentUser, db: Session, state: State) -> SharedOut:
    """A message with the card, prepared for Telegram.WebApp.shareMessage: Telegram downloads
    the picture from this site by an unguessable link."""
    bot = share_flow.bot_of(state)
    site = share_flow.site_of(state)
    card, image, t = await _draw(db, user, habit_id, state, bot)
    caption = cards.caption(card, t)
    return await share_flow.prepare(
        db, bot, site, user.id, image, caption, state.clock(), habit_id=habit_id
    )


@router.post("/habits/{habit_id}/card", status_code=204)
async def send_card(habit_id: ItemId, user: CurrentUser, db: Session, state: State) -> Response:
    """The card as a photo in the chat with the bot — the way to share it on clients that
    cannot share from a Mini App: the user forwards it."""
    bot = share_flow.bot_of(state)
    card, image, t = await _draw(db, user, habit_id, state, bot)
    await share_flow.send(bot, user.id, image, "habit.jpg", cards.caption(card, t))
    return Response(status_code=204)
