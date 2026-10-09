"""The one way the API's pictures reach Telegram, the habit card's and the forecast's alike: shared
from the Mini App through a prepared message, or sent as a photo to the chat with the bot — the
way to share on clients that cannot share from a Mini App: the user forwards it."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import ClientDecodeError, TelegramAPIError, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineQueryResultPhoto
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api.schemas import SharedOut
from assistant.api.state import AppState
from assistant.core.errors import UpstreamUnavailable, WriteForbidden
from assistant.core.services import sharing

log = logging.getLogger(__name__)


def bot_of(state: AppState) -> Bot:
    """The bot that sends the pictures; without one, sharing is off."""
    if state.bot is None:
        raise UpstreamUnavailable(service="telegram")
    return state.bot


def site_of(state: AppState) -> str:
    """«https://host» a shared picture's link points to: without it Telegram could not download
    the picture, and sharing from the app is off."""
    if state.site is None:
        raise UpstreamUnavailable(service="telegram")
    return state.site


async def bot_name(bot: Bot) -> str:
    """The bot's username for the picture's footer: asked once, then kept by the Bot."""
    try:
        me = await bot.me()
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("asking Telegram for the bot's name failed: %s", error)
        raise UpstreamUnavailable(service="telegram") from error
    return me.username or ""


def _moment(value: datetime | timedelta | int, now: datetime) -> datetime:
    """Telegram's «expiration_date» as aiogram gives it: from a real answer, Unix time."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, timedelta):
        return now + value
    return datetime.fromtimestamp(value, UTC)


async def prepare(
    db: AsyncSession,
    bot: Bot,
    site: str,
    user_id: int,
    image: bytes,
    caption: str,
    now: datetime,
    *,
    habit_id: int | None = None,
) -> SharedOut:
    """A message with the picture, prepared for Telegram.WebApp.shareMessage to any chat:
    Telegram downloads the picture from `site` by an unguessable link. It is kept while the
    message can be sent; when Telegram refuses the message, it goes at once."""
    token = await sharing.save(db, user_id, image, now, habit_id=habit_id)
    await db.commit()
    link = f"{site}/api/share/{token}.jpg"
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user_id,
            result=InlineQueryResultPhoto(
                id=token, photo_url=link, thumbnail_url=link, caption=caption
            ),
            allow_user_chats=True,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("preparing a shared picture for user %s failed: %s", user_id, error)
        await sharing.forget(db, token)
        await db.commit()
        raise UpstreamUnavailable(service="telegram") from error
    await sharing.keep_until(db, token, _moment(prepared.expiration_date, now), now)
    await db.commit()
    return SharedOut(prepared_id=prepared.id)


async def send(bot: Bot, user_id: int, image: bytes, filename: str, caption: str) -> None:
    """The picture as a photo in the chat with the bot. WriteForbidden when Telegram does not
    let the bot write to the user, so the app asks them to start the bot rather than calling the
    service down. `bot_blocked` stays the bot's: it marks a block when a message of its own fails
    and lifts it when the user writes."""
    try:
        await bot.send_photo(
            chat_id=user_id, photo=BufferedInputFile(image, filename=filename), caption=caption
        )
    except TelegramForbiddenError as error:  # a subclass of TelegramAPIError: caught first
        log.info("the bot may not write to user %s: %s", user_id, error)
        raise WriteForbidden() from error
    except (TelegramAPIError, ClientDecodeError) as error:
        log.warning("sending a picture to user %s failed: %s", user_id, error)
        raise UpstreamUnavailable(service="telegram") from error
