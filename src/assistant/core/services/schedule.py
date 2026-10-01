"""A user's timetable: connecting a source, refreshing it, reading its lessons, lesson alerts.

A source is downloaded (or, for a file, kept) and expanded into the lessons of a rolling
window; every refresh replaces them as a whole. Nothing is written until the new calendar
has been downloaded and parsed, so a failure never touches what was there before.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.calendars import Calendars, normalize
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.models import (
    Lesson,
    LessonAlert,
    ScheduleKind,
    ScheduleSource,
    User,
    WeekLabel,
)
from assistant.core.services import groups, ical
from assistant.core.timeutil import local_to_utc, utcnow

WINDOW_BEFORE = timedelta(days=7)
WINDOW_AFTER = timedelta(days=120)
REFRESH_EVERY = timedelta(hours=6)
REFRESH_GAP = timedelta(minutes=1)  # the least time between two refreshes asked by hand
STALE_AFTER = timedelta(days=3)
ALERT_MINUTES = (5, 10, 15, 30, 60)
ALERT_LATE = timedelta(minutes=10)  # an alert this late (the bot was down) is not sent
FILE_LIMIT = 2 * 1024 * 1024
TITLE_LENGTH = 100

# One calendar parse at a time per process: each child may take 15 s and 256 MiB, and uploads can
# arrive together; queued parses wait here, not in the default thread pool.
_PARSER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calendar-parser")


def window(now: datetime) -> tuple[datetime, datetime]:
    return now - WINDOW_BEFORE, now + WINDOW_AFTER


def next_refresh(user_id: int, now: datetime) -> datetime:
    # Spread over an hour by user id, so all sources do not go to MIREA at the same minute.
    return now + REFRESH_EVERY + timedelta(minutes=user_id % 60)


async def get_source(session: AsyncSession, user_id: int) -> ScheduleSource | None:
    return await session.get(ScheduleSource, user_id)


async def _timetable(body: bytes, user: User, now: datetime) -> ical.Timetable:
    start, end = window(now)
    # The parser runs in a child process with a time limit; wait for it off the event loop.
    parse = functools.partial(ical.parse_isolated, body, start, end, user.timezone)
    return await asyncio.get_running_loop().run_in_executor(_PARSER, parse)


async def _replace(session: AsyncSession, user_id: int, table: ical.Timetable) -> None:
    await session.execute(delete(Lesson).where(Lesson.user_id == user_id))
    await session.execute(delete(WeekLabel).where(WeekLabel.user_id == user_id))
    session.add_all(
        Lesson(
            user_id=user_id,
            uid=item.uid,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            title=item.title,
            kind=item.kind,
            room=item.room,
        )
        for item in table.lessons
    )
    session.add_all(
        WeekLabel(user_id=user_id, start_date=week.start, end_date=week.end, label=week.label)
        for week in table.weeks
    )
    await session.flush()


async def _store(
    session: AsyncSession,
    user: User,
    table: ical.Timetable,
    now: datetime,
    *,
    kind: ScheduleKind,
    title: str | None,
    mirea_id: int | None = None,
    url: str | None = None,
    body: bytes | None = None,
) -> ScheduleSource:
    source = await get_source(session, user.id)
    if source is None:
        source = ScheduleSource(user_id=user.id)
        session.add(source)
    source.kind = kind
    source.mirea_id = mirea_id
    source.url = url
    source.title = (title or "").strip()[:TITLE_LENGTH] or None
    source.body = body
    source.fetched_at = source.ok_at = now
    source.error = None
    source.next_refresh_at = next_refresh(user.id, now)
    await _replace(session, user.id, table)
    return source


async def connect_mirea(
    session: AsyncSession,
    user: User,
    group_id: int,
    calendars: Calendars,
    now: datetime | None = None,
) -> ScheduleSource:
    moment = now or utcnow()
    group = await groups.get(session, group_id)
    if group is None:
        raise NotFound(entity="group")
    url = groups.calendar_url(group_id)
    table = await _timetable(await calendars.fetch(url), user, moment)
    return await _store(
        session,
        user,
        table,
        moment,
        kind=ScheduleKind.MIREA,
        title=group.name,
        mirea_id=group_id,
        url=url,
    )


async def connect_url(
    session: AsyncSession,
    user: User,
    url: str,
    calendars: Calendars,
    now: datetime | None = None,
) -> ScheduleSource:
    moment = now or utcnow()
    link = normalize(url)  # a webcal:// link is kept as the https:// one it stands for
    table = await _timetable(await calendars.fetch(str(link)), user, moment)
    return await _store(
        session,
        user,
        table,
        moment,
        kind=ScheduleKind.URL,
        title=table.name or link.host,
        url=str(link),
    )


async def connect_file(
    session: AsyncSession,
    user: User,
    body: bytes,
    filename: str | None = None,
    now: datetime | None = None,
) -> ScheduleSource:
    if len(body) > FILE_LIMIT:
        raise InvalidInput(field="file", reason="too_large")
    moment = now or utcnow()
    table = await _timetable(body, user, moment)
    stem = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if stem.lower().endswith(".ics"):
        stem = stem[: -len(".ics")]
    return await _store(
        session,
        user,
        table,
        moment,
        kind=ScheduleKind.FILE,
        title=table.name or stem,
        body=body,
    )


async def refresh(
    session: AsyncSession,
    user: User,
    calendars: Calendars,
    now: datetime | None = None,
) -> ScheduleSource:
    """Download (or, for a file, re-read) the calendar and replace the lessons. A failure is
    only recorded on the source — the lessons already there stay."""
    source = await get_source(session, user.id)
    if source is None:
        raise NotFound(entity="schedule")
    moment = now or utcnow()
    try:
        if source.kind is ScheduleKind.FILE:
            body = source.body or b""
        else:
            body = await calendars.fetch(source.url or "")
        table = await _timetable(body, user, moment)
    except InvalidInput as error:
        source.error = str(error.params.get("reason") or "unreachable")[:32]
        source.fetched_at = moment
        source.next_refresh_at = next_refresh(user.id, moment)
        await session.flush()
        return source
    source.fetched_at = source.ok_at = moment
    source.error = None
    source.next_refresh_at = next_refresh(user.id, moment)
    await _replace(session, user.id, table)
    return source


async def postpone(session: AsyncSession, user_id: int, now: datetime) -> None:
    """Put the source off until its next regular refresh, so that one failing unexpectedly does
    not stay first in the queue. A source gone meanwhile is no error."""
    await session.execute(
        update(ScheduleSource)
        .where(ScheduleSource.user_id == user_id)
        .values(next_refresh_at=next_refresh(user_id, now))
    )


async def disconnect(session: AsyncSession, user_id: int) -> bool:
    source = await get_source(session, user_id)
    if source is None:
        return False
    await session.execute(delete(Lesson).where(Lesson.user_id == user_id))
    await session.execute(delete(WeekLabel).where(WeekLabel.user_id == user_id))
    await session.delete(source)
    await session.flush()
    return True


async def set_alert_minutes(
    session: AsyncSession, user_id: int, minutes: int | None
) -> ScheduleSource:
    if minutes is not None and minutes not in ALERT_MINUTES:
        raise InvalidInput(field="lesson_reminder_minutes", reason="invalid")
    source = await get_source(session, user_id)
    if source is None:
        raise NotFound(entity="schedule")
    source.lesson_reminder_minutes = minutes
    await session.flush()
    return source


def is_stale(source: ScheduleSource, now: datetime) -> bool:
    return source.ok_at is None or now - source.ok_at > STALE_AFTER


def refresh_wait(source: ScheduleSource, now: datetime) -> float:
    """Seconds until a refresh by hand is allowed again; 0 when it is allowed now."""
    return max(0.0, (source.fetched_at + REFRESH_GAP - now).total_seconds())


async def lessons_between(
    session: AsyncSession, user_id: int, start: datetime, end: datetime
) -> list[Lesson]:
    result = await session.scalars(
        select(Lesson)
        .where(Lesson.user_id == user_id, Lesson.starts_at >= start, Lesson.starts_at < end)
        .order_by(Lesson.starts_at, Lesson.title)
    )
    return list(result.all())


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    """The user's local day as a UTC interval."""
    start = local_to_utc(datetime.combine(day, time()), tz)
    return start, local_to_utc(datetime.combine(day + timedelta(days=1), time()), tz)


async def lessons_on(session: AsyncSession, user: User, day: date) -> list[Lesson]:
    return await lessons_between(session, user.id, *day_bounds(day, user.timezone))


async def lessons_ahead(session: AsyncSession, user_id: int, now: datetime) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(Lesson)
        .where(Lesson.user_id == user_id, Lesson.starts_at >= now)
    )
    return int(total or 0)


async def week_labels_between(
    session: AsyncSession, user_id: int, first: date, last: date
) -> list[WeekLabel]:
    """The labels of the weeks that touch the days first…last (both included)."""
    result = await session.scalars(
        select(WeekLabel)
        .where(
            WeekLabel.user_id == user_id,
            WeekLabel.start_date <= last,
            WeekLabel.end_date > first,
        )
        .order_by(WeekLabel.start_date)
    )
    return list(result.all())


def label_on(labels: Sequence[WeekLabel], day: date) -> str | None:
    return next((w.label for w in labels if w.start_date <= day < w.end_date), None)


async def week_label(session: AsyncSession, user_id: int, day: date) -> str | None:
    return label_on(await week_labels_between(session, user_id, day, day), day)


async def due_sources(session: AsyncSession, now: datetime, limit: int) -> list[int]:
    """Users whose source is due for its periodic refresh, the longest waiting first."""
    result = await session.scalars(
        select(ScheduleSource.user_id)
        .where(ScheduleSource.next_refresh_at <= now)
        .order_by(ScheduleSource.next_refresh_at)
        .limit(limit)
    )
    return list(result.all())


async def due_alerts(session: AsyncSession, now: datetime) -> list[tuple[Lesson, User, int]]:
    """Lessons whose alert is due now: its moment has come, it is at most ALERT_LATE old, the
    user wants alerts and can be written to, and it was not sent before."""
    horizon = now + timedelta(minutes=max(ALERT_MINUTES))
    rows = await session.execute(
        select(Lesson, User, ScheduleSource.lesson_reminder_minutes)
        .join(ScheduleSource, ScheduleSource.user_id == Lesson.user_id)
        .join(User, User.id == Lesson.user_id)
        .outerjoin(
            LessonAlert,
            (LessonAlert.user_id == Lesson.user_id)
            & (LessonAlert.uid == Lesson.uid)
            & (LessonAlert.starts_at == Lesson.starts_at),
        )
        .where(
            ScheduleSource.lesson_reminder_minutes.is_not(None),
            User.bot_blocked.is_(False),
            LessonAlert.user_id.is_(None),
            Lesson.starts_at > now,
            Lesson.starts_at <= horizon,
        )
        .order_by(Lesson.starts_at)
    )
    due: list[tuple[Lesson, User, int]] = []
    for lesson, user, minutes in rows:
        if minutes is None:
            continue
        moment = lesson.starts_at - timedelta(minutes=minutes)
        if moment <= now and now - moment <= ALERT_LATE:
            due.append((lesson, user, minutes))
    return due


async def mark_alerted(session: AsyncSession, lesson: Lesson, now: datetime) -> None:
    await session.execute(
        insert(LessonAlert)
        .values(user_id=lesson.user_id, uid=lesson.uid, starts_at=lesson.starts_at, sent_at=now)
        .on_conflict_do_nothing()
    )


async def forget_alerts(session: AsyncSession, before: datetime) -> int:
    result = await session.execute(delete(LessonAlert).where(LessonAlert.starts_at < before))
    return int(result.rowcount)  # type: ignore[attr-defined]
