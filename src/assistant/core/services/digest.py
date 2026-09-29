"""Everything needed for «Мой день» and the morning digest, in one call."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.clients.cbr import CbrClient, Rates
from assistant.core.clients.openmeteo import OpenMeteoClient
from assistant.core.errors import UpstreamUnavailable
from assistant.core.models import Reminder, User
from assistant.core.services import habits, notes, reminders, weather
from assistant.core.services.habits import HabitStats
from assistant.core.services.weather import WeatherNow
from assistant.core.timeutil import now_local, utcnow


@dataclass(frozen=True)
class TodayData:
    local_now: datetime
    part_of_day: str
    weather: WeatherNow | None
    reminders: list[Reminder]
    habits: list[HabitStats]
    habits_done: int
    habits_total: int
    notes_count: int
    rates: Rates | None
    best_streak: tuple[str, int] | None


def part_of_day(hour: int) -> str:
    if 5 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "day"
    if 17 <= hour <= 22:
        return "evening"
    return "night"


async def _weather(meteo: OpenMeteoClient, user: User) -> WeatherNow | None:
    try:
        return await weather.current(meteo, user.city, user.lat, user.lon)
    except UpstreamUnavailable:
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
    weather_now, rates = await asyncio.gather(_weather(meteo, user), _rates(cbr))
    items = await habits.list_with_stats(session, user, moment)
    best = max(
        (item for item in items if item.streak > 0), key=lambda item: item.streak, default=None
    )
    local = now_local(user.timezone, moment)
    return TodayData(
        local_now=local,
        part_of_day=part_of_day(local.hour),
        weather=weather_now,
        reminders=await reminders.today_for(session, user, moment),
        habits=items,
        habits_done=sum(1 for item in items if item.done_today),
        habits_total=len(items),
        notes_count=await notes.count(session, user.id),
        rates=rates,
        best_streak=(best.habit.name, best.streak) if best else None,
    )
