"""Core objects → API response models."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from babel.numbers import get_currency_name

from assistant.api.schemas import (
    AlertOut,
    BestStreak,
    CategoryTotalOut,
    CityOut,
    ClassesWeatherOut,
    CurrencyRateOut,
    ForecastCityOut,
    ForecastDayOut,
    ForecastHourOut,
    ForecastNowOut,
    ForecastOut,
    FoundCityOut,
    HabitDetailOut,
    HabitOut,
    MeOut,
    MoneyCategoryOut,
    MoneyEntryOut,
    MoneyMonthOut,
    MorningOut,
    NoteItemOut,
    NoteOut,
    PinnedNoteOut,
    RateHistoryOut,
    RateOut,
    RatePointOut,
    RatesAllOut,
    RatesOut,
    ReminderOut,
    RuleOut,
    ScheduleOut,
    TodayHabits,
    TodayLesson,
    TodayMoneyOut,
    TodayOut,
    TodayReminder,
    WeatherCityOut,
    WeatherOut,
)
from assistant.core.clients.cbr import Point, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import (
    MoneyCategory,
    MoneyEntry,
    Reminder,
    ScheduleSource,
    User,
    WeatherCity,
)
from assistant.core.money_style import OTHER
from assistant.core.services import digest, money, reminders, schedule, weather
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import HabitDetail, HabitStats
from assistant.core.services.money_month import Alert, CategoryTotal, Month
from assistant.core.services.notes import Item, NoteView
from assistant.core.services.recurrence import Rule, describe
from assistant.core.services.weather import Day, Forecast, Hour, WeatherNow
from assistant.core.services.weather import describe as describe_weather
from assistant.core.timeutil import to_local

# The hours after «now» in the forecast: the app's strip of 24 hours begins with «now» itself.
STRIP_HOURS = 23


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
        currency=user.currency,
        money_budget=user.money_budget,
    )


def found_city_out(city: City) -> FoundCityOut:
    return FoundCityOut(**asdict(city))


def weather_city_out(city: WeatherCity) -> WeatherCityOut:
    return WeatherCityOut(
        id=city.id,
        name=city.name,
        admin=city.admin,
        country=city.country,
        lat=city.lat,
        lon=city.lon,
        timezone=city.timezone,
        geo_id=city.geo_id,
    )


def _tips(now: WeatherNow, t: Translator) -> list[str]:
    return [t(tip.key, **tip.params) for tip in now.tips]


def weather_out(now: WeatherNow, t: Translator) -> WeatherOut:
    emoji, key = describe_weather(now.code, now.is_day)
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
        tips=_tips(now, t),
    )


def _clock(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def _hour_out(hour: Hour, t: Translator) -> ForecastHourOut:
    emoji, key = describe_weather(hour.code, hour.is_day)
    return ForecastHourOut(
        time=_clock(hour.at),
        emoji=emoji,
        description=t(key),
        temperature=hour.temperature,
        precip_chance=hour.precip_chance,
    )


def day_out(day: Day, t: Translator) -> ForecastDayOut:
    emoji, key = describe_weather(day.code)
    return ForecastDayOut(
        date=day.day,
        emoji=emoji,
        description=t(key),
        tmin=day.tmin,
        tmax=day.tmax,
        precip_chance=day.precip_chance,
    )


def forecast_out(
    forecast: Forecast, city: ForecastCityOut, now: datetime, t: Translator
) -> ForecastOut:
    """The city's forecast at the moment `now` (aware): its hours and days counted on the
    city's clock, from the hour going on and from the city's today."""
    local = weather.local_now(forecast, now)
    days = weather.days_from(forecast, local.date())
    first = days[0] if days else None
    polar = weather.polar(first) if first is not None else None
    sun = first if polar is None else None  # no times on a polar day or night
    current = forecast.now
    emoji, key = describe_weather(current.code, current.is_day)
    return ForecastOut(
        city=city,
        now=ForecastNowOut(
            temperature=current.temperature,
            feels_like=current.feels_like,
            wind=current.wind,
            gusts=current.gusts,
            humidity=current.humidity,
            is_day=current.is_day,
            emoji=emoji,
            description=t(key),
            precip_chance=weather.chance_after(forecast, local),
        ),
        tips=_tips(current, t),
        hours=[_hour_out(hour, t) for hour in weather.next_hours(forecast, local, STRIP_HOURS)],
        days=[day_out(day, t) for day in days],
        sunrise=_clock(sun.sunrise) if sun is not None and sun.sunrise is not None else None,
        sunset=_clock(sun.sunset) if sun is not None and sun.sunset is not None else None,
        polar=polar,  # type: ignore[arg-type]
    )


def rates_out(rates: Rates) -> RatesOut:
    return RatesOut(
        date=rates.day,
        usd=RateOut(value=rates.usd.value, change=rates.usd.change),
        eur=RateOut(value=rates.eur.value, change=rates.eur.change),
    )


def _habit_fields(stats: HabitStats) -> dict[str, object]:
    habit = stats.habit
    return {
        "id": habit.id,
        "name": habit.name,
        "emoji": habit.emoji,
        "color": habit.color,
        "weekly_goal": habit.weekly_goal,
        "created_on": habit.created_on,
        "day": stats.today,
        "done_today": stats.done_today,
        "streak": stats.streak,
        "streak_unit": stats.unit,
        "record": stats.record,
        "percent": stats.percent,
        "week_done": stats.week_done,
        "week_goal": stats.week_goal,
        "week": stats.week,
        "done_days": stats.done_days,
        "total_days": stats.total_days,
        "last_days": list(stats.last_days),
    }


def habit_out(stats: HabitStats) -> HabitOut:
    return HabitOut.model_validate(_habit_fields(stats))


def habit_detail_out(detail: HabitDetail) -> HabitDetailOut:
    return HabitDetailOut.model_validate(
        {**_habit_fields(detail.stats), "year_from": detail.year_start, "year": detail.year}
    )


def item_out(item: Item) -> NoteItemOut:
    return NoteItemOut(id=item.id, text=item.text, done=item.done)


def note_out(note: NoteView) -> NoteOut:
    return NoteOut(
        id=note.id,
        text=note.text,
        pinned=note.pinned,
        items=[item_out(item) for item in note.items],
        created_at=note.created_at,
        updated_at=note.updated_at,
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


def _tomorrow(data: TodayData, t: Translator) -> ForecastDayOut | None:
    """Tomorrow's weather in the evening of the user's day, as in «Мой день»."""
    day = digest.tomorrow_weather(data)
    return day_out(day, t) if day is not None else None


def _classes_weather(data: TodayData) -> ClassesWeatherOut | None:
    """The way to today's first class and back from the last one, whatever the time now."""
    found = digest.classes_weather(data)
    if found is None:
        return None
    return ClassesWeatherOut(
        start=_clock(found.start),
        start_temp=found.start_temp,
        start_chance=found.start_chance,
        end=_clock(found.end),
        end_temp=found.end_temp,
        end_chance=found.end_chance,
    )


def pinned_note_out(note: NoteView) -> PinnedNoteOut:
    return PinnedNoteOut(id=note.id, text=note.text, done=note.done, total=note.total)


def today_out(data: TodayData, t: Translator) -> TodayOut:
    """«Сегодня» of the user, on the clock data.local_now is on."""
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
        best_streak=BestStreak(
            name=data.best_streak.name,
            count=data.best_streak.length,
            unit=data.best_streak.unit,
        )
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
        money=TodayMoneyOut(
            currency=data.currency,
            today=data.spent_today,
            spent=data.money.spent,
            budget=data.money.budget,
            left=data.money.left,
            per_day=data.money.per_day,
            count=data.money.count,
        )
        if data.money is not None
        else None,
        tomorrow=_tomorrow(data, t),
        classes_weather=_classes_weather(data),
        pinned_notes=[pinned_note_out(note) for note in data.pinned],
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


def hundredths(amount: str) -> int:
    """«430.50» → 43050 (the schema checked the form)."""
    return int(Decimal(amount) * 100)


def category_out(category: MoneyCategory, t: Translator) -> MoneyCategoryOut:
    return MoneyCategoryOut(
        id=category.id,
        kind=category.kind,  # type: ignore[arg-type]
        name=money.name_of(category, t),
        emoji=category.emoji,
        hidden=category.hidden,
        can_hide=category.preset != OTHER[category.kind],
        budget=category.budget,
    )


def entry_out(entry: MoneyEntry) -> MoneyEntryOut:
    return MoneyEntryOut(
        id=entry.id,
        amount=entry.amount,
        category_id=entry.category_id,
        note=entry.note,
        day=entry.day,
    )


def _total_out(item: CategoryTotal) -> CategoryTotalOut:
    return CategoryTotalOut(
        category_id=item.category.id, amount=item.amount, share=item.share, left=item.left
    )


def month_out(
    month: Month,
    oldest: date | None,
    categories: list[MoneyCategory],
    entries: list[MoneyEntry],
    user: User,
    t: Translator,
) -> MoneyMonthOut:
    return MoneyMonthOut(
        month=month.first.strftime("%Y-%m"),
        first_month=None if oldest is None else oldest.strftime("%Y-%m"),
        currency=user.currency,
        spent=month.spent,
        income=month.income,
        balance=month.balance,
        budget=month.budget,
        left=month.left,
        per_day=month.per_day,
        expenses=[_total_out(item) for item in month.expenses],
        incomes=[_total_out(item) for item in month.incomes],
        days=month.days,
        categories=[category_out(item, t) for item in categories],
        entries=[entry_out(item) for item in entries],
    )


def alert_out(alert: Alert, t: Translator) -> AlertOut:
    category = alert.category
    return AlertOut(
        category_id=None if category is None else category.id,
        emoji=None if category is None else category.emoji,
        name=None if category is None else money.name_of(category, t),
        threshold=alert.threshold,
        spent=alert.spent,
        budget=alert.budget,
    )


def rates_all_out(rates: Rates, user: User) -> RatesAllOut:
    """USD, EUR and the user's currency first, the others by name in the user's language."""
    lang = user_language(user)
    first = ["USD", "EUR", user.currency]

    def name(code: str) -> str:
        found = str(get_currency_name(code, locale=lang))
        return found[:1].upper() + found[1:]

    def order(code: str) -> tuple[int, str]:
        return (first.index(code), "") if code in first else (len(first), name(code))

    return RatesAllOut(
        date=rates.day,
        currencies=[
            CurrencyRateOut(code=code, name=name(code), value=rate.value, change=rate.change)
            for code, rate in sorted(rates.currencies.items(), key=lambda item: order(item[0]))
        ],
    )


def history_out(code: str, points: list[Point]) -> RateHistoryOut:
    return RateHistoryOut(
        code=code, points=[RatePointOut(day=point.day, value=point.value) for point in points]
    )
