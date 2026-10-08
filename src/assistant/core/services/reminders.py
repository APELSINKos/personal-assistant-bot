"""One-off reminders: parsing user input, rules and the delivery state machine."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Reminder, ReminderStatus, Repeat, User
from assistant.core.services import recurrence
from assistant.core.services.phrases import Parsed
from assistant.core.services.recurrence import Rule
from assistant.core.timeutil import SUPPORTED_YEARS, local_to_utc, local_today, to_local, utcnow

log = logging.getLogger(__name__)

BACKOFF: tuple[int, ...] = (30, 60, 300, 900, 3600, 10800)
# Every delay in BACKOFF is used once; the attempt after the last delay is the final one.
MAX_FAILURES = len(BACKOFF) + 1

SNOOZE_KINDS = ("10m", "1h", "tomorrow")
_SNOOZE_DELAYS = {"10m": timedelta(minutes=10), "1h": timedelta(hours=1)}
# Two presses of the same button a few seconds apart (a double tap, a retried callback)
# target slightly different `until` moments; treat anything this close as the same snooze.
_SAME_SNOOZE = timedelta(seconds=60)
# The buttons under a delivered reminder work this long; a finished reminder is kept as long.
FIRED_TTL = timedelta(days=7)


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


async def _check_limit(session: AsyncSession, user_id: int) -> None:
    if await count_pending(session, user_id) >= LIMITS.reminders:
        raise LimitReached(entity="reminder", limit=LIMITS.reminders)


def rule_of(reminder: Reminder) -> Rule | None:
    if reminder.repeat is Repeat.NONE or reminder.time_local is None:
        return None
    if reminder.anchor_date is None:
        return None
    return Rule(
        repeat=reminder.repeat,
        time_local=reminder.time_local,
        anchor_date=reminder.anchor_date,
        weekdays=reminder.weekdays,
        interval_weeks=reminder.interval_weeks,
        month_day=reminder.month_day,
    )


def _set_rule(reminder: Reminder, rule: Rule | None) -> None:
    reminder.repeat = rule.repeat if rule else Repeat.NONE
    reminder.time_local = rule.time_local if rule else None
    reminder.anchor_date = rule.anchor_date if rule else None
    reminder.weekdays = rule.weekdays if rule else None
    reminder.interval_weeks = rule.interval_weeks if rule else 1
    reminder.month_day = rule.month_day if rule else None


def _schedule(reminder: Reminder, moment: datetime) -> None:
    reminder.occurrence_at = reminder.due_at = reminder.next_attempt_at = moment
    reminder.attempts = 0
    reminder.last_error = None


def _to_utc(when_local: datetime, tz: str) -> datetime:
    # Checked before any conversion: a moment by the calendar's edge overflows, if not here
    # then later (on «+10 мин» or after a move east), and breaks every list that shows it.
    if when_local.year not in SUPPORTED_YEARS:
        raise InvalidInput(field="when", reason="invalid")
    return local_to_utc(when_local, tz)


def _biweekly_anchor(rule: Rule, tz: str, moment: datetime) -> Rule:
    """A fresh every-other-week rule (anchored today or later) starts at the first matching
    weekday: move the anchor there so that day counts as its own "on" week — the app and the
    bot then agree on when such a rule starts. An anchor already before local today (an
    existing series being edited) keeps its parity exactly as it already is.
    """
    if rule.interval_weeks != 2 or rule.anchor_date < local_today(tz, moment):
        return rule
    local_after = to_local(moment, tz).replace(tzinfo=None)
    first_day = recurrence.first_matching_day(rule, rule.anchor_date, local_after)
    return replace(rule, anchor_date=first_day) if first_day is not None else rule


async def create(
    session: AsyncSession,
    user: User,
    text: str,
    when_local: datetime,
    now: datetime | None = None,
) -> Reminder:
    cleaned = clean_text(text)
    due_at = _to_utc(when_local, user.timezone)
    if due_at <= (now or utcnow()):
        raise InvalidInput(field="when", reason="past")
    await _check_limit(session, user.id)
    reminder = Reminder(user_id=user.id, text=cleaned, status=ReminderStatus.PENDING)
    _set_rule(reminder, None)
    _schedule(reminder, due_at)
    session.add(reminder)
    await session.flush()
    return reminder


async def create_repeating(
    session: AsyncSession,
    user: User,
    text: str,
    rule: Rule,
    now: datetime | None = None,
) -> Reminder:
    cleaned = clean_text(text)
    rule.validate()
    await _check_limit(session, user.id)
    moment = now or utcnow()
    rule = _biweekly_anchor(rule, user.timezone, moment)
    first = recurrence.next_after(rule, moment, user.timezone)
    # A series never carries a firing from before it existed: the anchor starts no earlier
    # than the first real firing (still an "on" week for an every-other-week rule).
    rule = replace(rule, anchor_date=max(rule.anchor_date, to_local(first, user.timezone).date()))
    reminder = Reminder(user_id=user.id, text=cleaned, status=ReminderStatus.PENDING)
    _set_rule(reminder, rule)
    _schedule(reminder, first)
    session.add(reminder)
    await session.flush()
    return reminder


async def create_from(
    session: AsyncSession,
    user: User,
    parsed: Parsed,
    now: datetime | None = None,
) -> Reminder:
    """A reminder from an understood phrase; the text is checked before the time."""
    moment = now or utcnow()
    clean_text(parsed.text)
    local_now = to_local(moment, user.timezone)
    rule = parsed.rule(local_now)
    if rule is not None:
        return await create_repeating(session, user, parsed.text, rule, moment)
    when = parsed.when(local_now)
    if when is None:
        raise InvalidInput(field="when", reason="needs_time")
    return await create(session, user, parsed.text, when, moment)


async def get_owned(session: AsyncSession, user_id: int, reminder_id: int) -> Reminder | None:
    reminder = await session.get(Reminder, reminder_id)
    return reminder if reminder is not None and reminder.user_id == user_id else None


def _same_schedule(new: Rule, current: Rule | None) -> bool:
    """Whether an edit's rule fires exactly as the stored one. Its anchor is noise (the API
    fills in today when none is given) — except the first day of an every-other-week rule,
    which the form shows and lets the user move."""
    if current is None:
        return False
    if new.interval_weeks == 2 and new.anchor_date != current.anchor_date:
        return False
    return replace(new, anchor_date=current.anchor_date) == current


async def update_reminder(
    session: AsyncSession,
    user: User,
    reminder_id: int,
    *,
    text: str | None = None,
    when_local: datetime | None = None,
    rule: Rule | None = None,
    now: datetime | None = None,
) -> Reminder:
    reminder = await get_owned(session, user.id, reminder_id)
    if reminder is None or reminder.status is not ReminderStatus.PENDING:
        raise NotFound(entity="reminder")
    moment = now or utcnow()
    # Every check runs before any field is touched, so a rejected edit leaves the row as-is.
    cleaned = clean_text(text) if text is not None else None
    if rule is not None and _same_schedule(rule, rule_of(reminder)):
        rule.validate()
        # The form sends the whole rule with every edit: a text-only edit keeps the series'
        # own firings (rescheduling from now could skip today's or flip its weeks).
        if cleaned is not None:
            reminder.text = cleaned
    elif rule is not None:
        rule.validate()
        rule = _biweekly_anchor(rule, user.timezone, moment)
        first = recurrence.next_after(rule, moment, user.timezone)
        rule = replace(
            rule, anchor_date=max(rule.anchor_date, to_local(first, user.timezone).date())
        )
        if cleaned is not None:
            reminder.text = cleaned
        reminder.parent_id = None  # a snoozed copy turned into a repeat is its own series
        _set_rule(reminder, rule)
        _schedule(reminder, first)
    elif when_local is not None:
        due_at = _to_utc(when_local, user.timezone)
        # The form only speaks minutes: its own moment sent back unchanged (even an overdue
        # one) is no reschedule and no past check.
        unchanged = reminder.repeat is Repeat.NONE and due_at == reminder.due_at.replace(
            second=0, microsecond=0
        )
        if not unchanged and due_at <= moment:
            raise InvalidInput(field="when", reason="past")
        if cleaned is not None:
            reminder.text = cleaned
        if not unchanged:
            _set_rule(reminder, None)
            _schedule(reminder, due_at)
    elif cleaned is not None:
        reminder.text = cleaned
    await session.flush()
    return reminder


def snooze_until(kind: str, fired_at: datetime, tz: str, now: datetime) -> datetime:
    """«+10 мин» / «+1 ч» from now; «Завтра» — the firing's local time on the next day."""
    if kind == "tomorrow":
        clock = to_local(fired_at, tz).time()
        tomorrow = local_today(tz, now) + timedelta(days=1)
        return local_to_utc(datetime.combine(tomorrow, clock), tz)
    return now + _SNOOZE_DELAYS[kind]


async def snooze(
    session: AsyncSession,
    user: User,
    reminder_id: int,
    until: datetime,
    now: datetime | None = None,
) -> Reminder:
    reminder = await get_owned(session, user.id, reminder_id)
    if reminder is None or reminder.status in (
        ReminderStatus.CANCELLED,
        ReminderStatus.FAILED,
        ReminderStatus.DONE,
    ):
        raise NotFound(entity="reminder")
    if until <= (now or utcnow()):
        raise InvalidInput(field="until", reason="past")
    if reminder.repeat is not Repeat.NONE:
        rule = rule_of(reminder)
        if rule is not None and (
            recurrence.next_after(rule, until - timedelta(microseconds=1), user.timezone) == until
        ):
            # The series itself already fires exactly then: nothing to snooze, no duplicate.
            return reminder
        existing = await session.scalar(
            select(Reminder).where(
                Reminder.parent_id == reminder.id,
                Reminder.status == ReminderStatus.PENDING,
                Reminder.due_at >= until - _SAME_SNOOZE,
                Reminder.due_at <= until + _SAME_SNOOZE,
            )
        )
        if existing is not None:
            # A double tap (or a retried callback) must not pile up duplicate copies.
            return existing
        # The series keeps its own schedule; the snoozed firing becomes a one-off copy.
        await _check_limit(session, user.id)
        copy = Reminder(
            user_id=user.id,
            text=reminder.text,
            status=ReminderStatus.PENDING,
            parent_id=reminder.id,
        )
        _set_rule(copy, None)
        _schedule(copy, until)
        session.add(copy)
        await session.flush()
        return copy
    if reminder.status is not ReminderStatus.PENDING:
        # Sent (not pending) until now: re-pending it needs a free slot, like a new reminder.
        await _check_limit(session, user.id)
    reminder.status = ReminderStatus.PENDING
    _schedule(reminder, until)
    await session.flush()
    return reminder


async def done(session: AsyncSession, user_id: int, reminder_id: int) -> bool:
    reminder = await get_owned(session, user_id, reminder_id)
    if reminder is None or reminder.status in (ReminderStatus.CANCELLED, ReminderStatus.FAILED):
        return False
    if reminder.repeat is Repeat.NONE:
        reminder.status = ReminderStatus.DONE
    await session.flush()
    return True


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


def shown_at(reminder: Reminder, tz: str, now: datetime) -> datetime:
    """The firing a delivery reports: for a repeat, the latest one missed so far."""
    rule = rule_of(reminder)
    if rule is None:
        return reminder.due_at
    return recurrence.latest_up_to(rule, now, reminder.occurrence_at, tz)


def mark_delivered(reminder: Reminder, now: datetime, tz: str) -> None:
    rule = rule_of(reminder)
    if rule is None:
        mark_sent(reminder, now)
        return
    reminder.sent_at = now
    _schedule(reminder, recurrence.next_after(rule, now, tz))


def give_up(reminder: Reminder, error: str, now: datetime, tz: str) -> None:
    """This firing will never be delivered: a one-off fails, a repeat moves on."""
    rule = rule_of(reminder)
    if rule is None:
        mark_failed(reminder, error)
        return
    _schedule(reminder, recurrence.next_after(rule, now, tz))
    reminder.last_error = error[:500]


def schedule_retry(
    reminder: Reminder,
    now: datetime,
    error: str,
    retry_after: float | None = None,
    tz: str | None = None,
) -> None:
    reminder.last_error = error[:500]
    if retry_after is not None:
        reminder.next_attempt_at = now + timedelta(seconds=retry_after)
        return
    reminder.attempts += 1
    if reminder.attempts >= MAX_FAILURES:
        # No reminder text in the log — only the id and the error.
        log.error(
            "reminder %s gave up after %d attempts: %s", reminder.id, reminder.attempts, error
        )
        if tz is not None and rule_of(reminder) is not None:
            give_up(reminder, error, now, tz)
        else:
            mark_failed(reminder, error)
        return
    reminder.next_attempt_at = now + timedelta(seconds=BACKOFF[reminder.attempts - 1])


async def expire_stale(
    session: AsyncSession,
    user_id: int,
    now: datetime,
    tz: str,
    max_age: timedelta = timedelta(hours=24),
) -> int:
    """After a long pause (the user had blocked the bot): old one-offs are dropped, repeats
    move on to their next firing instead of arriving in a burst."""
    result = await session.execute(
        update(Reminder)
        .where(
            Reminder.user_id == user_id,
            Reminder.status == ReminderStatus.PENDING,
            Reminder.repeat == Repeat.NONE,
            Reminder.due_at < now - max_age,
        )
        .values(status=ReminderStatus.FAILED, last_error="expired")
    )
    stale = (
        await session.scalars(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.PENDING,
                Reminder.repeat != Repeat.NONE,
                Reminder.due_at < now - max_age,
            )
        )
    ).all()
    for reminder in stale:
        rule = rule_of(reminder)
        if rule is not None:
            _schedule(reminder, recurrence.next_after(rule, now, tz))
    await session.flush()
    return int(result.rowcount) + len(stale)  # type: ignore[attr-defined]


async def forget_finished(session: AsyncSession, now: datetime) -> int:
    """Delete the sent, done, failed or cancelled reminders nothing can reach any more: never
    delivered, or delivered longer ago than the buttons under the message work. A snoozed copy
    outlives its series (its parent_id becomes NULL)."""
    result = await session.execute(
        delete(Reminder).where(
            Reminder.status != ReminderStatus.PENDING,
            or_(Reminder.sent_at.is_(None), Reminder.sent_at < now - FIRED_TTL),
        )
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def reschedule_repeating(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
    *,
    previous_tz: str | None = None,
) -> int:
    """After a move: every repeat keeps its local time in the new zone.

    With `previous_tz`, a pending firing whose local day (in the old zone) still fires under
    the rule keeps that same day's moment (never earlier than `now`): moving west right after
    a firing does not fire again the same evening, and moving east past the local time fires
    at once instead of waiting for tomorrow.
    """
    moment = now or utcnow()
    rows = (
        await session.scalars(
            select(Reminder).where(
                Reminder.user_id == user.id,
                Reminder.status == ReminderStatus.PENDING,
                Reminder.repeat != Repeat.NONE,
            )
        )
    ).all()
    for reminder in rows:
        rule = rule_of(reminder)
        if rule is None:
            continue
        next_due = None
        if previous_tz is not None:
            same_day = to_local(reminder.due_at, previous_tz).date()
            if recurrence.fires_on(rule, same_day):
                next_due = max(moment, recurrence.moment_on(rule, same_day, user.timezone))
        if next_due is None:
            next_due = recurrence.next_after(rule, moment, user.timezone)
        _schedule(reminder, next_due)
    await session.flush()
    return len(rows)


async def between(
    session: AsyncSession, user: User, start: datetime, end: datetime
) -> list[tuple[Reminder, datetime]]:
    """Pending one-offs and the firings of repeats in [start, end), by moment."""
    found: list[tuple[Reminder, datetime]] = []
    for reminder in await pending(session, user.id):
        rule = rule_of(reminder)
        if rule is None:
            if start <= reminder.due_at < end:
                found.append((reminder, reminder.due_at))
        else:
            found.extend(
                (reminder, moment) for moment in recurrence.between(rule, start, end, user.timezone)
            )
    found.sort(key=lambda pair: (pair[1], pair[0].id))
    return found


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
