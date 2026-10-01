"""The calendar: every day of a range with its reminders and lessons, in the user's city
zone, with the timetable's week labels."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.deps import CurrentUser, Session
from assistant.api.schemas import (
    AgendaDayOut,
    AgendaItemOut,
    AgendaOut,
    LessonItemOut,
    ReminderItemOut,
)
from assistant.api.views import user_translator
from assistant.core.errors import InvalidInput
from assistant.core.services import reminders, schedule
from assistant.core.services.recurrence import describe
from assistant.core.timeutil import SUPPORTED_YEARS, local_to_utc, to_local

router = APIRouter(tags=["agenda"])
MAX_DAYS = 62


@router.get("/agenda", response_model=AgendaOut)
async def agenda(
    user: CurrentUser,
    db: Session,
    start_day: Annotated[date, Query(alias="from")],
    end_day: Annotated[date, Query(alias="to")],
) -> AgendaOut:
    # Checked before any date arithmetic: a year far outside this range can overflow it.
    if start_day.year not in SUPPORTED_YEARS or end_day.year not in SUPPORTED_YEARS:
        raise InvalidInput(field="to", reason="range")
    if end_day < start_day or (end_day - start_day).days >= MAX_DAYS:
        raise InvalidInput(field="to", reason="range")
    tz = user.timezone
    start = local_to_utc(datetime.combine(start_day, time()), tz)
    end = local_to_utc(datetime.combine(end_day + timedelta(days=1), time()), tz)
    t = user_translator(user)
    days: dict[date, list[AgendaItemOut]] = {
        start_day + timedelta(days=i): [] for i in range((end_day - start_day).days + 1)
    }
    for reminder, moment in await reminders.between(db, user, start, end):
        local = to_local(moment, tz)
        rule = reminders.rule_of(reminder)
        days.setdefault(local.date(), []).append(
            ReminderItemOut(
                kind="reminder",
                id=reminder.id,
                time=local.strftime("%H:%M"),
                text=reminder.text,
                repeat=reminder.repeat.value,
                description=describe(rule, t) if rule else None,
            )
        )
    for lesson in await schedule.lessons_between(db, user.id, start, end):
        local = to_local(lesson.starts_at, tz)
        days.setdefault(local.date(), []).append(
            LessonItemOut(
                kind="lesson",
                time=local.strftime("%H:%M"),
                end=to_local(lesson.ends_at, tz).strftime("%H:%M"),
                title=lesson.title,
                lesson_kind=lesson.kind,
                room=lesson.room,
            )
        )
    labels = await schedule.week_labels_between(db, user.id, start_day, end_day)
    return AgendaOut(
        days=[
            AgendaDayOut(
                date=day,
                label=schedule.label_on(labels, day),
                items=sorted(items, key=lambda item: item.time),
            )
            for day, items in days.items()
        ]
    )
