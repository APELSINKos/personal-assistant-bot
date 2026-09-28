"""Background delivery inside the bot process: reminders with retries, the morning digest."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import partial

from aiogram import Bot
from aiogram.exceptions import (
    ClientDecodeError,
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
        except ClientDecodeError as error:  # a non-JSON body, usually an HTML 502/504: temporary
            return Delivery(False, error=f"decode: {error.message}")
        except TelegramAPIError as error:  # 5xx, conflicts, anything else: temporary
            return Delivery(False, error=f"{type(error).__name__}: {error.message}")
        return Delivery(True)

    async def _update_reminder(self, reminder_id: int, mutate: Callable[[Reminder], None]) -> None:
        """Re-fetch one reminder in its own session and commit a single mutation.

        Never holds a write transaction open across a network await: each call opens,
        writes and commits before returning. A reminder gone by the time we get here
        (e.g. the user was deleted meanwhile) is silently skipped.
        """
        async with self._sessionmaker() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is not None:
                mutate(reminder)
                await session.commit()

    async def _fail_and_block(self, reminder_id: int, user_id: int, error: str) -> None:
        async with self._sessionmaker() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is not None:
                reminders.mark_failed(reminder, error)
            await users.mark_blocked(session, user_id)
            await session.commit()

    async def deliver_reminders(self, now: datetime) -> int:
        sent = 0
        async with self._sessionmaker() as session:
            batch = await reminders.due(session, now)
        # The read session above is closed before any send; each outcome below is then
        # written in its own short session, so one reminder's failure (a decode error, a
        # busy database, a bug) cannot corrupt or abort the delivery of the others.
        blocked: set[int] = set()
        for reminder, user in batch:
            if user.id in blocked:
                continue
            try:
                delivery = await self._send(
                    user.id, reminder_text(reminder, user, now, _translator(user))
                )
                if delivery.retry_after is not None:
                    await self._update_reminder(
                        reminder.id,
                        partial(
                            reminders.schedule_retry,
                            now=now,
                            error=delivery.error,
                            retry_after=delivery.retry_after,
                        ),
                    )
                    log.warning("Telegram asked to wait %.0f s", delivery.retry_after)
                    break
                if delivery.ok:
                    await self._update_reminder(reminder.id, partial(reminders.mark_sent, now=now))
                    sent += 1
                elif delivery.blocked:
                    await self._fail_and_block(reminder.id, user.id, delivery.error)
                    blocked.add(user.id)
                    log.info("reminder %s failed permanently: %s", reminder.id, delivery.error)
                elif delivery.permanent:
                    await self._update_reminder(
                        reminder.id, partial(reminders.mark_failed, error=delivery.error)
                    )
                    log.info("reminder %s failed permanently: %s", reminder.id, delivery.error)
                else:
                    await self._update_reminder(
                        reminder.id,
                        partial(reminders.schedule_retry, now=now, error=delivery.error),
                    )
                    log.warning("reminder %s not delivered: %s", reminder.id, delivery.error)
            except Exception as error:
                # An unexpected failure (a busy database, a formatting bug) must not pin
                # this reminder at the head of the queue and must not stop the rest of
                # the batch: log it, push the reminder back with the normal backoff, and
                # move on. No reminder text in the log — only ids and error types.
                log.exception("reminder %s failed", reminder.id)
                await self._update_reminder(
                    reminder.id,
                    partial(reminders.schedule_retry, now=now, error=type(error).__name__),
                )
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
            if not delivery.ok:
                log.warning("morning digest for user %s not delivered: %s", user.id, delivery.error)
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
