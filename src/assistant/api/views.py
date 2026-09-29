"""Core objects → API response models."""

from __future__ import annotations

from assistant.api.schemas import (
    BestStreak,
    CityOut,
    HabitOut,
    MeOut,
    MorningOut,
    NoteOut,
    RateOut,
    RatesOut,
    ReminderOut,
    TodayHabits,
    TodayOut,
    TodayReminder,
    WeatherOut,
)
from assistant.core.clients.cbr import Rates
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import Note, Reminder, User
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import HabitStats
from assistant.core.services.weather import WeatherNow, describe
from assistant.core.timeutil import to_local


def user_language(user: User) -> str:
    return resolve_language(user.language, user.tg_language)


def user_translator(user: User) -> Translator:
    return translator(user_language(user))


def me_out(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        language=user_language(user),  # type: ignore[arg-type]
        language_setting=user.language or "auto",  # type: ignore[arg-type]
        city=CityOut(name=user.city, lat=user.lat, lon=user.lon, timezone=user.timezone),
        morning=MorningOut(enabled=user.morning_enabled, time=user.morning_time),
    )


def weather_out(now: WeatherNow, t: Translator) -> WeatherOut:
    emoji, key = describe(now.code)
    return WeatherOut(
        city=now.city,
        temperature=now.temperature,
        feels_like=now.feels_like,
        wind=now.wind,
        code=now.code,
        emoji=emoji,
        description=t(key),
        tmin=now.tmin,
        tmax=now.tmax,
        tips=[t(tip.key, **tip.params) for tip in now.tips],
    )


def rates_out(rates: Rates) -> RatesOut:
    return RatesOut(
        date=rates.day,
        usd=RateOut(value=rates.usd.value, change=rates.usd.change),
        eur=RateOut(value=rates.eur.value, change=rates.eur.change),
    )


def habit_out(stats: HabitStats) -> HabitOut:
    return HabitOut(
        id=stats.habit.id,
        name=stats.habit.name,
        created_on=stats.habit.created_on,
        done_today=stats.done_today,
        streak=stats.streak,
        done_days=stats.done_days,
        total_days=stats.total_days,
        last_days=list(stats.last_days),
    )


def note_out(note: Note) -> NoteOut:
    return NoteOut(
        id=note.id, text=note.text, created_at=note.created_at, updated_at=note.updated_at
    )


def reminder_out(reminder: Reminder, tz: str) -> ReminderOut:
    local = to_local(reminder.due_at, tz)
    return ReminderOut(
        id=reminder.id,
        text=reminder.text,
        due_at=reminder.due_at,
        due_local=local.strftime("%Y-%m-%dT%H:%M"),
        status=str(reminder.status),
    )


def today_out(data: TodayData, t: Translator) -> TodayOut:
    zone = data.local_now.tzinfo
    return TodayOut(
        date=data.local_now.date(),
        part_of_day=data.part_of_day,  # type: ignore[arg-type]
        weather=weather_out(data.weather, t) if data.weather is not None else None,
        reminders_today=[
            TodayReminder(
                id=r.id,
                text=r.text,
                time=r.due_at.astimezone(zone).strftime("%H:%M"),
                due_at=r.due_at,
            )
            for r in data.reminders
        ],
        habits=TodayHabits(
            done=data.habits_done,
            total=data.habits_total,
            items=[habit_out(stats) for stats in data.habits],
        ),
        notes_count=data.notes_count,
        rates=rates_out(data.rates) if data.rates is not None else None,
        best_streak=BestStreak(name=data.best_streak[0], days=data.best_streak[1])
        if data.best_streak is not None
        else None,
    )
