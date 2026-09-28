"""Background delivery inside the bot process: reminders with retries, the morning digest."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.bot import texts
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import FsmState, Reminder, User
from assistant.core.services import digest, reminders, users
from assistant.core.timeutil import digest_window_date, now_local, to_local, utcnow

log = logging.getLogger(__name__)

LATE_AFTER = timedelta(minutes=5)
FSM_TTL = timedelta(hours=24)
CLEANUP_EVERY = timedelta(hours=1)


@dataclass(frozen=True)
class Delivery:
    ok: bool
    retry_after: float | None = None  # Telegram asked to wait (429)
    blocked: bool = False  # 403: the user blocked the bot or deleted the account
    permanent: bool = False  # 400: this message will never be accepted
    error: str = ""


def _translator(user: User) -> Translator:
    return translator(resolve_language(user.language, user.tg_language))


def reminder_text(reminder: Reminder, user: User, now: datetime, t: Translator) -> str:
    if now - reminder.due_at <= LATE_AFTER:
        return t("reminder-fire", text=reminder.text)
    same_day = (
        to_local(reminder.due_at, user.timezone).date() == to_local(now, user.timezone).date()
    )
    when = (
        texts.local_time(reminder.due_at, user.timezone)
        if same_day
        else texts.short_moment(reminder.due_at, user.timezone, t.lang, now)
    )
    return t("reminder-fire-late", text=reminder.text, when=when)


class Scheduler:
    def __init__(
        self,
        bot: Bot,
        sessionmaker: async_sessionmaker[AsyncSession],
        meteo: OpenMeteoClient,
        cbr: CbrClient,
        *,
        interval: float = 20.0,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._bot = bot
        self._sessionmaker = sessionmaker
        self._meteo = meteo
        self._cbr = cbr
        self._interval = interval
        self._clock = clock
        self._last_cleanup: datetime | None = None

    async def run(self) -> None:
        log.info("Scheduler started, every %.0f s", self._interval)
        while True:
            await self.tick()
            await asyncio.sleep(self._interval)

    async def tick(self) -> None:
        now = self._clock()
        jobs: list[tuple[str, Callable[[datetime], Awaitable[int]]]] = [
            ("reminders", self.deliver_reminders),
            ("digests", self.send_digests),
        ]
        if self._last_cleanup is None or now - self._last_cleanup >= CLEANUP_EVERY:
            jobs.append(("cleanup", self.cleanup))
            self._last_cleanup = now
        for name, job in jobs:
            try:
                await job(now)
            except Exception:
                log.exception("scheduler job %s failed", name)

    async def _send(self, chat_id: int, text: str) -> Delivery:
        try:
            await self._bot.send_message(chat_id, text)
        except TelegramRetryAfter as error:
            return Delivery(False, retry_after=float(error.retry_after), error="retry_after")
        except TelegramForbiddenError as error:
            return Delivery(False, blocked=True, error=error.message)
        except TelegramBadRequest as error:
            return Delivery(False, permanent=True, error=error.message)
        except TelegramNetworkError as error:
            return Delivery(False, error=f"network: {error.message}")
        except TelegramAPIError as error:  # 5xx, conflicts, anything else: temporary
            return Delivery(False, error=f"{type(error).__name__}: {error.message}")
        return Delivery(True)

    async def deliver_reminders(self, now: datetime) -> int:
        sent = 0
        async with self._sessionmaker() as session:
            blocked: set[int] = set()
            for reminder, user in await reminders.due(session, now):
                if user.id in blocked:
                    continue
                delivery = await self._send(
                    user.id, reminder_text(reminder, user, now, _translator(user))
                )
                if delivery.ok:
                    reminders.mark_sent(reminder, now)
                    sent += 1
                elif delivery.retry_after is not None:
                    reminders.schedule_retry(reminder, now, delivery.error, delivery.retry_after)
                    await session.commit()
                    log.warning("Telegram asked to wait %.0f s", delivery.retry_after)
                    break
                elif delivery.blocked:
                    reminders.mark_failed(reminder, delivery.error)
                    await users.mark_blocked(session, user.id)
                    blocked.add(user.id)
                elif delivery.permanent:
                    reminders.mark_failed(reminder, delivery.error)
                else:
                    reminders.schedule_retry(reminder, now, delivery.error)
                    log.warning("reminder %s not delivered: %s", reminder.id, delivery.error)
                await session.commit()
        return sent

    async def send_digests(self, now: datetime) -> int:
        async with self._sessionmaker() as session:
            candidates = (
                await session.scalars(
                    select(User).where(User.morning_enabled.is_(True), User.bot_blocked.is_(False))
                )
            ).all()
        # The session is closed; the loaded attributes stay readable on the detached objects.
        sent = 0
        for user in candidates:
            day = digest_window_date(now_local(user.timezone, now), user.morning_time)
            if day is None or user.last_morning_date == day:
                continue
            try:
                delivery = await self._digest(user.id, day, now)
            except Exception:
                # One broken user must not stop the others; their own session is gone already.
                log.exception("morning digest for user %s failed", user.id)
                continue
            sent += int(delivery.ok)
            if delivery.retry_after is not None:
                break
        return sent

    async def _digest(self, user_id: int, day: date, now: datetime) -> Delivery:
        async with self._sessionmaker() as session:
            user = await session.get(User, user_id)
            if user is None:
                return Delivery(False, permanent=True, error="user is gone")
            t = _translator(user)
            data = await digest.today(session, user, self._meteo, self._cbr, now)
            delivery = await self._send(
                user.id, texts.morning_text(data, user.first_name or t("friend"), t)
            )
            if delivery.ok or delivery.permanent:
                user.last_morning_date = day
            elif delivery.blocked:
                user.bot_blocked = True
            await session.commit()
        return delivery

    async def cleanup(self, now: datetime) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(FsmState).where(FsmState.updated_at < now - FSM_TTL)
            )
            await session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]
