"""Background delivery inside the bot process: reminders with retries, lesson alerts, the morning
digest. Schedule refreshes run beside the ticks: a calendar download or parse takes seconds, and
reminders and lesson alerts must not wait for it."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
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
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.bot import texts
from assistant.bot.keyboards import fired_markup
from assistant.core.clients.calendars import Calendars
from assistant.core.clients.cbr import CbrClient
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.errors import NotFound
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import FsmState, Lesson, Reminder, User
from assistant.core.services import digest, reminders, schedule, sharing, users
from assistant.core.timeutil import digest_window_date, now_local, to_local, utcnow

log = logging.getLogger(__name__)

LATE_AFTER = timedelta(minutes=5)
FSM_TTL = timedelta(hours=24)
CLEANUP_EVERY = timedelta(hours=1)
ALERTS_KEPT = timedelta(days=2)  # sent lesson alerts are remembered this long
REFRESH_BATCH = 2  # sources per refresh pass, a download each: stop() waits for the pass in flight


@dataclass(frozen=True)
class Delivery:
    ok: bool
    retry_after: float | None = None  # Telegram asked to wait (429)
    blocked: bool = False  # 403: the user blocked the bot or deleted the account
    permanent: bool = False  # 400: this message will never be accepted
    error: str = ""


def _translator(user: User) -> Translator:
    return translator(resolve_language(user.language, user.tg_language))


def reminder_text(
    reminder: Reminder, user: User, shown: datetime, now: datetime, t: Translator
) -> str:
    if now - shown <= LATE_AFTER:
        return t("reminder-fire", text=reminder.text)
    same_day = to_local(shown, user.timezone).date() == to_local(now, user.timezone).date()
    when = (
        texts.local_time(shown, user.timezone)
        if same_day
        else texts.short_moment(shown, user.timezone, t.lang, now)
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
        calendars: Calendars | None = None,
    ) -> None:
        self._bot = bot
        self._calendars = calendars
        self._sessionmaker = sessionmaker
        self._meteo = meteo
        self._cbr = cbr
        self._interval = interval
        self._clock = clock
        self._last_cleanup: datetime | None = None
        self._stopping = asyncio.Event()
        self._refreshing: asyncio.Task[None] | None = None

    async def run(self) -> None:
        log.info("Scheduler started, every %.0f s", self._interval)
        try:
            while not self._stopping.is_set():
                await self.tick()
                # Sleep until the next tick, but wake up at once when stop() is called.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._refreshing is not None:
                await self._refreshing
        finally:
            # Cancelled (the shutdown grace ran out): the refresh must not outlive the ticks, and
            # run() returns only once it has wound down — its session closes before the engine
            # is disposed of.
            if self._refreshing is not None:
                self._refreshing.cancel()
                await asyncio.wait({self._refreshing})
        log.info("Scheduler stopped")

    def stop(self) -> None:
        """Finish the current tick and the schedule refresh in flight (their writes included)
        and return from run()."""
        self._stopping.set()

    async def tick(self) -> None:
        now = self._clock()
        self._start_refresh(now)
        jobs: list[tuple[str, Callable[[datetime], Awaitable[int]]]] = [
            ("reminders", self.deliver_reminders),
            ("lessons", self.send_lesson_alerts),
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

    def _start_refresh(self, now: datetime) -> None:
        # A refresh downloads and parses calendars, and a parse may queue behind users' uploads:
        # it runs as a task of its own, one at a time; the first tick after it ends starts the
        # next one.
        if self._calendars is None:
            return
        if self._refreshing is not None and not self._refreshing.done():
            return
        self._refreshing = asyncio.create_task(self._refresh(now), name="schedule-refresh")

    async def _refresh(self, now: datetime) -> None:
        try:
            await self.refresh_schedules(now)
        except Exception:
            log.exception("scheduler job schedules failed")

    async def _send(
        self,
        chat_id: int,
        text: str,
        markup: InlineKeyboardMarkup | None = None,
        *,
        link_preview_options: LinkPreviewOptions | None = None,
    ) -> Delivery:
        try:
            await self._bot.send_message(
                chat_id, text, reply_markup=markup, link_preview_options=link_preview_options
            )
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

    async def _fail_and_block(
        self, reminder_id: int, user_id: int, error: str, now: datetime, tz: str
    ) -> None:
        async with self._sessionmaker() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is not None:
                reminders.give_up(reminder, error, now, tz)
            await users.mark_blocked(session, user_id)
            await session.commit()

    async def deliver_reminders(self, now: datetime) -> int:
        sent = 0
        async with self._sessionmaker() as session:
            batch = await reminders.due(session, now)
        # The read session above is closed before any send; each outcome below is then
        # written in its own short session, so one reminder's failure (a busy database, a
        # bug) cannot corrupt or abort the delivery of the others. A 429 or a failing
        # network/Telegram stops the batch instead: the rest stay due for the next tick.
        blocked: set[int] = set()
        for reminder, user in batch:
            if user.id in blocked:
                continue
            try:
                t = _translator(user)
                shown = reminders.shown_at(reminder, user.timezone, now)
                delivery = await self._send(
                    user.id,
                    reminder_text(reminder, user, shown, now, t),
                    fired_markup(t, reminder.id, shown),
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
                    await self._update_reminder(
                        reminder.id, partial(reminders.mark_delivered, now=now, tz=user.timezone)
                    )
                    sent += 1
                elif delivery.blocked:
                    await self._fail_and_block(
                        reminder.id, user.id, delivery.error, now, user.timezone
                    )
                    blocked.add(user.id)
                    log.info("reminder %s: gave up this firing: %s", reminder.id, delivery.error)
                elif delivery.permanent:
                    await self._update_reminder(
                        reminder.id,
                        partial(reminders.give_up, error=delivery.error, now=now, tz=user.timezone),
                    )
                    log.info("reminder %s: gave up this firing: %s", reminder.id, delivery.error)
                else:
                    await self._update_reminder(
                        reminder.id,
                        partial(
                            reminders.schedule_retry,
                            now=now,
                            error=delivery.error,
                            tz=user.timezone,
                        ),
                    )
                    log.warning("reminder %s not delivered: %s", reminder.id, delivery.error)
                    # The network or Telegram is failing: the rest of the batch would most
                    # likely fail the same way, each after a full timeout, stalling the tick.
                    # They stay due and are tried on the next tick.
                    break
            except Exception as error:
                # An unexpected failure (a busy database, a formatting bug) must not pin
                # this reminder at the head of the queue and must not stop the rest of
                # the batch: log it, push the reminder back with the normal backoff, and
                # move on. No reminder text in the log — only ids and error types.
                log.exception("reminder %s failed", reminder.id)
                await self._update_reminder(
                    reminder.id,
                    partial(
                        reminders.schedule_retry,
                        now=now,
                        error=type(error).__name__,
                        tz=user.timezone,
                    ),
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
            try:
                day = digest_window_date(now_local(user.timezone, now), user.morning_time)
                if day is None or user.last_morning_date == day:
                    continue
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

    async def send_lesson_alerts(self, now: datetime) -> int:
        """«🎓 Через 15 мин: …» for the lessons whose alert is due. An alert is remembered only
        once Telegram took it (or refused it for good); a network failure leaves it for the next
        tick, as long as it is still in time."""
        async with self._sessionmaker() as session:
            due = await schedule.due_alerts(session, now)
        sent = 0
        blocked: set[int] = set()
        for lesson, user, _minutes in due:
            if user.id in blocked:
                continue
            left = max(1, math.ceil((lesson.starts_at - now).total_seconds() / 60))
            delivery = await self._send(
                user.id, texts.lesson_alert_text(lesson, left, _translator(user))
            )
            if delivery.retry_after is not None:
                break
            if delivery.ok or delivery.permanent:
                await self._remember_alert(lesson, now)
                sent += int(delivery.ok)
            elif delivery.blocked:
                async with self._sessionmaker() as session:
                    await users.mark_blocked(session, user.id)
                    await session.commit()
                blocked.add(user.id)
            else:
                log.warning("lesson alert for user %s not delivered: %s", user.id, delivery.error)
                break
        return sent

    async def _remember_alert(self, lesson: Lesson, now: datetime) -> None:
        async with self._sessionmaker() as session:
            await schedule.mark_alerted(session, lesson, now)
            await session.commit()

    async def refresh_schedules(self, now: datetime) -> int:
        """Refresh the schedule sources that are due, a few per pass."""
        if self._calendars is None:
            return 0
        async with self._sessionmaker() as session:
            due = await schedule.due_sources(session, now, REFRESH_BATCH)
        refreshed = 0
        for user_id in due:
            try:
                async with self._sessionmaker() as session:
                    user = await session.get(User, user_id)
                    if user is None:
                        continue
                    source = await schedule.refresh(session, user, self._calendars, now)
                    error = source.error
                    await session.commit()
            except NotFound:
                continue  # the schedule was disconnected meanwhile
            except Exception as failure:
                # An unexpected failure (the parser child did not start, a busy database) would
                # keep this source first in the queue: every pass would download it again and
                # fail the same way while the others wait. It waits for its next turn instead.
                log.warning(
                    "schedule of user %s not refreshed: %r", user_id, failure, exc_info=True
                )
                await self._postpone(user_id, now)
                continue
            if error:
                log.warning("schedule of user %s not refreshed: %s", user_id, error)
            refreshed += 1
        return refreshed

    async def _postpone(self, user_id: int, now: datetime) -> None:
        async with self._sessionmaker() as session:
            await schedule.postpone(session, user_id, now)
            await session.commit()

    async def cleanup(self, now: datetime) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(FsmState).where(FsmState.updated_at < now - FSM_TTL)
            )
            alerts = await schedule.forget_alerts(session, now - ALERTS_KEPT)
            cards = await sharing.prune(session, now)
            await session.commit()
        return int(result.rowcount) + alerts + cards  # type: ignore[attr-defined]
