"""Habits: list with statistics, one habit with its year, create, change, delete, mark a day,
and the share card — shared from the app or sent to the bot chat."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import ClientDecodeError, TelegramAPIError
from aiogram.types import BufferedInputFile, InlineQueryResultPhoto
from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

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
from assistant.core.errors import NotFound, UpstreamUnavailable
from assistant.core.i18n import Translator
from assistant.core.models import User
from assistant.core.services import cards, habits, sharing
from assistant.core.timeutil import local_today

log = logging.getLogger(__name__)
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


def _moment(value: datetime | timedelta | int, now: datetime) -> datetime:
    """Telegram's «expiration_date» as aiogram gives it: from a real answer, Unix time."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, timedelta):
        return now + value
    return datetime.fromtimestamp(value, UTC)


def _bot(state: AppState) -> Bot:
    if state.bot is None:
        raise UpstreamUnavailable(service="telegram")
    return state.bot


async def _draw(
    db: AsyncSession, user: User, habit_id: int, state: AppState, bot: Bot
) -> tuple[cards.Card, bytes, Translator]:
    """The user's card for the habit, within their budget of cards a minute."""
    detail = await habits.detail(db, user, habit_id, state.clock())  # a foreign habit: 404
    wait = state.cards.check(user.id)
    if wait is not None:
        raise RateLimited(wait)
    try:
        me = await bot.me()  # asked once, then kept by the Bot
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("asking Telegram for the bot's name failed: %s", error)
        raise UpstreamUnavailable(service="telegram") from error
    t = user_translator(user)
    card = cards.card_for(detail, local_today(user.timezone, state.clock()), me.username or "")
    return card, await cards.draw_card(card, t), t


@router.post("/habits/{habit_id}/share", response_model=SharedOut)
async def share_habit(habit_id: ItemId, user: CurrentUser, db: Session, state: State) -> SharedOut:
    """A message with the card, prepared for Telegram.WebApp.shareMessage: Telegram downloads
    the picture from this site by an unguessable link."""
    bot = _bot(state)
    if state.site is None:
        raise UpstreamUnavailable(service="telegram")
    card, image, t = await _draw(db, user, habit_id, state, bot)
    now = state.clock()
    token = await sharing.save(db, user.id, habit_id, image, now)
    await db.commit()
    link = f"{state.site}/api/share/{token}.jpg"
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.id,
            result=InlineQueryResultPhoto(
                id=token, photo_url=link, thumbnail_url=link, caption=cards.caption(card, t)
            ),
            allow_user_chats=True,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("preparing a shared card for user %s failed: %s", user.id, error)
        await sharing.forget(db, token)
        await db.commit()
        raise UpstreamUnavailable(service="telegram") from error
    await sharing.keep_until(db, token, _moment(prepared.expiration_date, now), now)
    await db.commit()
    return SharedOut(prepared_id=prepared.id)


@router.post("/habits/{habit_id}/card", status_code=204)
async def send_card(habit_id: ItemId, user: CurrentUser, db: Session, state: State) -> Response:
    """The card as a photo in the chat with the bot — the way to share it on clients that
    cannot share from a Mini App: the user forwards it."""
    bot = _bot(state)
    card, image, t = await _draw(db, user, habit_id, state, bot)
    try:
        await bot.send_photo(
            chat_id=user.id,
            photo=BufferedInputFile(image, filename="habit.jpg"),
            caption=cards.caption(card, t),
        )
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("sending a card to user %s failed: %s", user.id, error)
        raise UpstreamUnavailable(service="telegram") from error
    return Response(status_code=204)
