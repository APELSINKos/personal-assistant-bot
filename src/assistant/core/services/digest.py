"""Everything needed for «Мой день» and the morning digest, in one call."""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.cbr import CbrClient, Rates
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.errors import UpstreamUnavailable
from assistant.core.models import Lesson, Reminder, User
from assistant.core.services import habits, money_month, notes, reminders, schedule, weather
from assistant.core.services.habits import HabitStats, Streak
from assistant.core.services.money_month import Month
from assistant.core.services.notes import NoteView
from assistant.core.services.weather import ClassesWeather, Day, Forecast, WeatherNow
from assistant.core.timeutil import now_local, utcnow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TodayData:
    local_now: datetime
    part_of_day: str
    weather: WeatherNow | None  # the forecast's now
    reminders: list[Reminder]
    habits: list[HabitStats]
    habits_done: int
    habits_total: int
    notes_count: int
    rates: Rates | None
    best_streak: Streak | None
    has_schedule: bool = False  # a timetable is connected
    lessons: list[Lesson] = field(default_factory=list)  # today's, in the user's zone
    week_label: str | None = None  # «5 неделя»
    money: Month | None = None  # this month's money
    spent_today: int = 0
    spent_yesterday: int = 0
    currency: str = "RUB"
    # The home city's forecast, None without weather: tomorrow and the way to the classes.
    forecast: Forecast | None = None
    pinned: list[NoteView] = field(default_factory=list)  # the first pinned notes, with items


# «Завтра» is shown from this hour of the user's clock to midnight, in «Мой день» and on
# «Сегодня» alike.
TOMORROW_FROM = 17


def tomorrow_weather(data: TodayData) -> Day | None:
    """Tomorrow's weather in the evening of the user's day, from TOMORROW_FROM on the user's
    clock, when the forecast has that day."""
    if data.forecast is None or data.local_now.hour < TOMORROW_FROM:
        return None
    return weather.tomorrow(data.forecast, data.local_now.date())


def classes_span(data: TodayData) -> tuple[datetime, datetime] | None:
    """When today's classes begin and end: the earliest start and the latest end (aware
    moments). None without lessons."""
    if not data.lessons:
        return None
    start = min(lesson.starts_at for lesson in data.lessons)
    end = max(lesson.ends_at for lesson in data.lessons)
    return start, end


def classes_weather(data: TodayData) -> ClassesWeather | None:
    """The weather of the way to today's classes and back — the whole day's answer, whatever the
    time now: the bot and the app drop what is over. None without the forecast, lessons or the
    forecast's hour of the end."""
    span = classes_span(data)
    if data.forecast is None or span is None:
        return None
    # The times are shown on the user's clock, the one local_now is on: a ZoneInfo (to_local),
    # whose str is the zone's name.
    return weather.classes_weather(data.forecast, *span, str(data.local_now.tzinfo))


def part_of_day(hour: int) -> str:
    if 5 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "day"
    if 17 <= hour <= 22:
        return "evening"
    return "night"


async def home_forecast(meteo: OpenMeteoClient, user: User) -> Forecast | None:
    """The home city's forecast, or None: the day is shown without weather. The scheduler asks
    for it alone first while a morning digest may still wait for the weather."""
    try:
        return await weather.forecast(meteo, user.city, user.lat, user.lon)
    except UpstreamUnavailable:
        return None
    except Exception as error:
        # An answer the parser trips over must not cost the user the whole day. Only where it
        # tripped goes to the log: the answer itself tells where the user is.
        place = traceback.extract_tb(error.__traceback__)[-1]
        log.warning(
            "the forecast could not be read: %s in %s, line %s",
            type(error).__name__,
            place.name,
            place.lineno,
        )
        return None


async def _rates(cbr: CbrClient) -> Rates | None:
    try:
        return await cbr.daily()
    except UpstreamUnavailable:
        return None


async def today(
    session: AsyncSession,
    user: User,
    meteo: OpenMeteoClient,
    cbr: CbrClient,
    now: datetime | None = None,
) -> TodayData:
    moment = now or utcnow()
    forecast, rates = await asyncio.gather(home_forecast(meteo, user), _rates(cbr))
    items = await habits.list_with_stats(session, user, moment)
    local = now_local(user.timezone, moment)
    source = await schedule.get_source(session, user.id)
    lessons: list[Lesson] = []
    label: str | None = None
    if source is not None:
        lessons = await schedule.lessons_on(session, user, local.date())
        label = await schedule.week_label(session, user.id, local.date())
    month = await money_month.month(session, user, now=moment)
    yesterday = local.date() - timedelta(days=1)
    return TodayData(
        local_now=local,
        part_of_day=part_of_day(local.hour),
        weather=forecast.now if forecast is not None else None,
        reminders=await reminders.today_for(session, user, moment),
        habits=items,
        habits_done=sum(1 for item in items if item.done_today),
        habits_total=len(items),
        notes_count=await notes.count(session, user.id),
        rates=rates,
        best_streak=habits.pick_best(items),
        has_schedule=source is not None,
        lessons=lessons,
        week_label=label,
        money=month,
        spent_today=month.days[local.day - 1] or 0,
        spent_yesterday=await money_month.spent_on(session, user, yesterday),
        currency=user.currency,
        forecast=forecast,
        pinned=await notes.pinned(session, user.id),
    )
