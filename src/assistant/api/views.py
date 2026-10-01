"""Core objects → API response models."""

from __future__ import annotations

from datetime import datetime

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
    RuleOut,
    ScheduleOut,
    TodayHabits,
    TodayLesson,
    TodayOut,
    TodayReminder,
    WeatherOut,
)
from assistant.core.clients.cbr import Rates
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import Note, Reminder, ScheduleSource, User
from assistant.core.services import reminders, schedule
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import HabitStats
from assistant.core.services.recurrence import Rule, describe
from assistant.core.services.weather import WeatherNow
from assistant.core.services.weather import describe as describe_weather
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
        can_write=user.can_write,
    )


def weather_out(now: WeatherNow, t: Translator) -> WeatherOut:
    emoji, key = describe_weather(now.code)
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


def rule_out(rule: Rule | None) -> RuleOut | None:
    if rule is None:
        return None
    return RuleOut(
        repeat=rule.repeat.value,  # type: ignore[arg-type]
        time_local=rule.time_local,
        weekdays=rule.weekdays,
        interval_weeks=rule.interval_weeks,
        month_day=rule.month_day,
        anchor_date=rule.anchor_date,
    )


def reminder_out(reminder: Reminder, tz: str, t: Translator) -> ReminderOut:
    local = to_local(reminder.due_at, tz)
    rule = reminders.rule_of(reminder)
    return ReminderOut(
        id=reminder.id,
        text=reminder.text,
        due_at=reminder.due_at,
        due_local=local.strftime("%Y-%m-%dT%H:%M"),
        status=str(reminder.status),
        repeat=reminder.repeat.value,
        rule=rule_out(rule),
        description=describe(rule, t) if rule else None,
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
        has_schedule=data.has_schedule,
        lessons=[
            TodayLesson(
                time=lesson.starts_at.astimezone(zone).strftime("%H:%M"),
                end=lesson.ends_at.astimezone(zone).strftime("%H:%M"),
                title=lesson.title,
                kind=lesson.kind,
                room=lesson.room,
                starts_at=lesson.starts_at,
                ends_at=lesson.ends_at,
            )
            for lesson in data.lessons
        ],
        week_label=data.week_label,
    )


def schedule_out(source: ScheduleSource, now: datetime, lessons_ahead: int) -> ScheduleOut:
    return ScheduleOut(
        kind=source.kind.value,
        title=source.title,
        mirea_id=source.mirea_id,
        url=source.url,
        fetched_at=source.fetched_at,
        ok_at=source.ok_at,
        error=source.error,
        stale=schedule.is_stale(source, now),
        lesson_reminder_minutes=source.lesson_reminder_minutes,
        lessons_ahead=lessons_ahead,
    )
