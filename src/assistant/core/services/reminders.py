"""One-off reminders: parsing user input, rules and the delivery state machine."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached
from assistant.core.models import Reminder, ReminderStatus, User
from assistant.core.timeutil import local_to_utc, local_today, parse_hhmm, utcnow

log = logging.getLogger(__name__)

BACKOFF: tuple[int, ...] = (30, 60, 300, 900, 3600, 10800)
# Every delay in BACKOFF is used once; the attempt after the last delay is the final one.
MAX_FAILURES = len(BACKOFF) + 1
_DAY = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$")


def parse_when(text: str, now_local: datetime) -> datetime | None:
    """'HH:MM' (today, or tomorrow if already reached), 'DD.MM HH:MM', 'DD.MM.YYYY HH:MM'."""
    parts = text.split()
    wall_now = now_local.replace(tzinfo=None)
    try:
        if len(parts) == 1:
            hhmm = parse_hhmm(parts[0])
            if hhmm is None:
                return None
            hours, minutes = (int(x) for x in hhmm.split(":"))
            moment = wall_now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            return moment + timedelta(days=1) if moment <= wall_now else moment
        if len(parts) == 2:
            day_match, hhmm = _DAY.match(parts[0]), parse_hhmm(parts[1])
            if day_match is None or hhmm is None:
                return None
            year = int(day_match.group(3)) if day_match.group(3) else wall_now.year
            hours, minutes = (int(x) for x in hhmm.split(":"))
            return datetime(year, int(day_match.group(2)), int(day_match.group(1)), hours, minutes)
    except ValueError:
        return None
    return None


def clean_text(text: str) -> str:
    cleaned = text.strip()
    if not 1 <= len(cleaned) <= LIMITS.reminder_length:
        raise InvalidInput(field="text", reason="length", limit=LIMITS.reminder_length)
    return cleaned


async def count_pending(session: AsyncSession, user_id: int) -> int:
    query = (
        select(func.count())
        .select_from(Reminder)
        .where(Reminder.user_id == user_id, Reminder.status == ReminderStatus.PENDING)
    )
    return int(await session.scalar(query) or 0)


async def create(
    session: AsyncSession,
    user: User,
    text: str,
    when_local: datetime,
    now: datetime | None = None,
) -> Reminder:
    cleaned = clean_text(text)
    due_at = local_to_utc(when_local, user.timezone)
    if due_at <= (now or utcnow()):
        raise InvalidInput(field="when", reason="past")
    if await count_pending(session, user.id) >= LIMITS.reminders:
        raise LimitReached(entity="reminder", limit=LIMITS.reminders)
    reminder = Reminder(
        user_id=user.id,
        text=cleaned,
        due_at=due_at,
        next_attempt_at=due_at,
        status=ReminderStatus.PENDING,
        attempts=0,
    )
    session.add(reminder)
    await session.flush()
    return reminder


async def pending(session: AsyncSession, user_id: int) -> list[Reminder]:
    result = await session.scalars(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.status == ReminderStatus.PENDING)
        .order_by(Reminder.due_at, Reminder.id)
    )
    return list(result.all())


async def cancel(session: AsyncSession, user_id: int, reminder_id: int) -> bool:
    result = await session.execute(
        update(Reminder)
        .where(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.status == ReminderStatus.PENDING,
        )
        .values(status=ReminderStatus.CANCELLED)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def due(
    session: AsyncSession, now: datetime, limit: int = 100
) -> list[tuple[Reminder, User]]:
    result = await session.execute(
        select(Reminder, User)
        .join(User, User.id == Reminder.user_id)
        .where(
            Reminder.status == ReminderStatus.PENDING,
            Reminder.next_attempt_at <= now,
            User.bot_blocked.is_(False),
        )
        .order_by(Reminder.next_attempt_at, Reminder.id)
        .limit(limit)
    )
    return [(row[0], row[1]) for row in result.all()]


def mark_sent(reminder: Reminder, now: datetime) -> None:
    reminder.status = ReminderStatus.SENT
    reminder.sent_at = now
    reminder.last_error = None


def mark_failed(reminder: Reminder, error: str) -> None:
    reminder.status = ReminderStatus.FAILED
    reminder.last_error = error[:500]


def schedule_retry(
    reminder: Reminder,
    now: datetime,
    error: str,
    retry_after: float | None = None,
) -> None:
    reminder.last_error = error[:500]
    if retry_after is not None:
        reminder.next_attempt_at = now + timedelta(seconds=retry_after)
        return
    reminder.attempts += 1
    if reminder.attempts >= MAX_FAILURES:
        mark_failed(reminder, error)
        # No reminder text in the log — only the id and the error.
        log.error(
            "reminder %s gave up after %d attempts: %s", reminder.id, reminder.attempts, error
        )
        return
    reminder.next_attempt_at = now + timedelta(seconds=BACKOFF[reminder.attempts - 1])


async def expire_stale(
    session: AsyncSession,
    user_id: int,
    now: datetime,
    max_age: timedelta = timedelta(hours=24),
) -> int:
    result = await session.execute(
        update(Reminder)
        .where(
            Reminder.user_id == user_id,
            Reminder.status == ReminderStatus.PENDING,
            Reminder.due_at < now - max_age,
        )
        .values(status=ReminderStatus.FAILED, last_error="expired")
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def _day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    start = local_to_utc(datetime.combine(day, time()), tz_name)
    end = local_to_utc(datetime.combine(day + timedelta(days=1), time()), tz_name)
    return start, end


async def today_for(
    session: AsyncSession, user: User, now: datetime | None = None
) -> list[Reminder]:
    start, end = _day_bounds(local_today(user.timezone, now), user.timezone)
    result = await session.scalars(
        select(Reminder)
        .where(
            Reminder.user_id == user.id,
            Reminder.status == ReminderStatus.PENDING,
            Reminder.due_at >= start,
            Reminder.due_at < end,
        )
        .order_by(Reminder.due_at)
    )
    return list(result.all())
