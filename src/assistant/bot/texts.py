"""Service data → message text. Pure functions without I/O."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from babel.dates import format_date, format_datetime

from assistant.bot.keyboards import preview
from assistant.bot.money_texts import money, month_name
from assistant.core.clients.cbr import Rates
from assistant.core.i18n import (
    Translator,
    format_day,
    format_number,
    format_short_day,
    format_weekday,
)
from assistant.core.models import Lesson, Reminder, ScheduleSource
from assistant.core.services import digest, reminders, weather
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import Streak
from assistant.core.services.notes import NoteView
from assistant.core.services.phrases import Parsed
from assistant.core.services.recurrence import describe, local_days
from assistant.core.services.weather import Day, Forecast, Hour, Tip, WeatherNow
from assistant.core.services.weather import describe as describe_weather
from assistant.core.timeutil import to_local, utcnow

NO_VALUE = "—"
# Telegram takes a message of up to 4096 characters counted in UTF-16 code units, where an emoji
# outside the BMP is two; a longer one is refused for good. Every message that carries many texts
# of the user's or of a calendar is kept within this, measured the same way, a margin below.
TEXT_LIMIT = 3900
# With up to 20 pending reminders at 200 characters each, rendering all of them could blow the
# limit on its own. Cap the rendered list and summarise the rest in one line instead.
DAY_REMINDERS_SHOWN = 10
# A day has a handful of lessons; a calendar full of events is capped the same way.
DAY_LESSONS_SHOWN = 10
# A lesson line keeps its time and as much of the name as fits: titles and rooms come from outside
# calendars, and ten long ones next to the reminders would push «Мой день» and the morning digest
# past the limit. 120 still leaves real MIREA lessons whole, room included.
LESSON_NAME_LIMIT = 120
# «🕐 По часам»: every hour from the next one, half a day ahead.
HOURS_SHOWN = 12
# A chance of rain or snow is worth a mention from this many percent on. The classes line has a
# threshold of its own (weather.CLASSES_CHANCE).
CHANCE_SHOWN = 20
# A pinned note in «Мой день» is one short line: the start of its text.
PINNED_PREVIEW = 40


def utf16_len(text: str) -> int:
    """The length of a message as Telegram counts it."""
    return len(text.encode("utf-16-le")) // 2


def temp(value: float | None) -> str:
    """14.2 → '+14°C', -3.7 → '-4°C', 0.2 → '0°C'."""
    if value is None:
        return NO_VALUE
    rounded = round(value)
    return "0°C" if rounded == 0 else f"{rounded:+d}°C"


def temp_range(low: float | None, high: float | None) -> str:
    return f"{temp(low).removesuffix('°C')}…{temp(high)}"


def local_time(moment: datetime, tz: tzinfo | str) -> str:
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    return moment.astimezone(zone).strftime("%H:%M")


def tip_lines(tips: list[Tip], t: Translator) -> list[str]:
    return [t(tip.key, **tip.params) for tip in tips]


def _now_values(now: WeatherNow, t: Translator) -> dict[str, object]:
    """The weather now as its lines name it: «🌤 Москва: +10°C, малооблачно», the moon at night."""
    emoji, key = describe_weather(now.code, now.is_day)
    return {"emoji": emoji, "city": now.city, "temp": temp(now.temperature), "description": t(key)}


def _now_line(now: WeatherNow, t: Translator) -> str:
    return t("weather-now", **_now_values(now, t))


def _with_credit(lines: list[str], t: Translator) -> str:
    """A view of the weather: its lines, then where the data come from. Open-Meteo's licence
    (CC BY 4.0) asks for the source next to the data."""
    return "\n".join([*lines, "", t("weather-credit")])


def weather_text(now: WeatherNow, t: Translator) -> str:
    """«🌤 Погода»: now, how it feels and the wind, today's range, every tip."""
    wind = NO_VALUE if now.wind is None else str(round(now.wind))
    return _with_credit(
        [
            _now_line(now, t),
            t("weather-feels", feels=temp(now.feels_like), wind=wind),
            t("weather-range", range=temp_range(now.tmin, now.tmax)),
            "",
            *tip_lines(now.tips, t),
        ],
        t,
    )


def _chance_shown(chance: int | None) -> bool:
    return chance is not None and chance >= CHANCE_SHOWN


def _same_clock(forecast: Forecast, now: datetime, user_tz: str) -> bool:
    """Whether the place's clock shows the user's time: the two offsets at the moment `now`. The
    zone's utcoffset of a UTC moment, read as a wall time, would be off near a change of clocks."""
    place = now.astimezone(forecast.tz).utcoffset()
    return place == now.astimezone(ZoneInfo(user_tz)).utcoffset()


def _hour_line(hour: Hour, t: Translator) -> str:
    """«15:00 ☁️ +7°C», with «💧 40 %» from CHANCE_SHOWN on."""
    emoji, _ = describe_weather(hour.code, hour.is_day)
    values = {"time": hour.at.strftime("%H:%M"), "emoji": emoji, "temp": temp(hour.temperature)}
    if _chance_shown(hour.precip_chance):
        return t("weather-hour-chance", chance=hour.precip_chance, **values)
    return t("weather-hour", **values)


def _date_line(day: date, today: date, t: Translator) -> str:
    """The line before the first hour of `day`: «Завтра, 6 октября». Twelve hours reach no
    further than tomorrow; a later day comes only after hours missing from the forecast and is
    named by its date alone."""
    if day == today + timedelta(days=1):
        return t("weather-next-day", date=format_day(day, t.lang))
    return format_day(day, t.lang)


def hours_text(forecast: Forecast, now: datetime, user_tz: str, t: Translator) -> str:
    """«🕐 По часам» of the forecast's place at the moment `now` (aware) for a user who lives by
    `user_tz`: the next HOURS_SHOWN hours on the place's clock, marked as local time when it
    differs from the user's, with a date line before the first hour of the next day."""
    local = weather.local_now(forecast, now)
    title = "weather-hours-title"
    if not _same_clock(forecast, now, user_tz):
        title = "weather-hours-title-local"
    lines = [t(title, city=forecast.now.city), ""]
    hours = weather.next_hours(forecast, local, HOURS_SHOWN)
    day = local.date()
    for hour in hours:
        if hour.at.date() != day:
            day = hour.at.date()
            lines.append(_date_line(day, local.date(), t))
        lines.append(_hour_line(hour, t))
    if not hours:
        lines.append(t("weather-hours-none"))
    return _with_credit(lines, t)


def _week_label(day: date, today: date, t: Translator) -> str:
    """«Сегодня», «Завтра», then «ср, 7 окт.»: a week needs neither «Послезавтра» nor a year."""
    offset = (day - today).days
    if offset == 0:
        return t("day-today")
    if offset == 1:
        return t("day-tomorrow")
    return format_short_day(day, t.lang)


def _day_line(day: Day, today: date, t: Translator) -> str:
    """«Сегодня ☁️ +2…+7°C», with «💧 80 %» from CHANCE_SHOWN on: the icon is the day's heaviest
    weather, and the chance tells how likely it is to come."""
    emoji, _ = describe_weather(day.code)
    values = {
        "label": _week_label(day.day, today, t),
        "emoji": emoji,
        "range": temp_range(day.tmin, day.tmax),
    }
    if _chance_shown(day.precip_chance):
        return t("weather-day-chance", chance=day.precip_chance, **values)
    return t("weather-day", **values)


def week_text(forecast: Forecast, now: datetime, t: Translator) -> str:
    """«📅 Неделя» of the forecast's place at the moment `now` (aware): up to seven days from the
    place's today. Just after midnight a forecast kept from the day before has six; a forecast
    whose every day lacks its minimum or maximum has none, and the view says so."""
    today = weather.local_now(forecast, now).date()
    lines = [t("weather-week-title", city=forecast.now.city), ""]
    days = weather.days_from(forecast, today)
    lines += [_day_line(day, today, t) for day in days]
    if not days:
        lines.append(t("weather-days-none"))
    return _with_credit(lines, t)


def _reminder_lines(data: TodayData, t: Translator, shown: int) -> list[str]:
    """The first `shown` reminders, then «…и ещё N» for the rest."""
    zone = data.local_now.tzinfo or ZoneInfo("UTC")
    listed = data.reminders[:shown]
    lines = [t("list-item-time", time=local_time(r.due_at, zone), text=r.text) for r in listed]
    hidden = len(data.reminders) - len(listed)
    if hidden > 0:
        lines.append(t("list-more", count=hidden))
    return lines


def lesson_line(lesson: Lesson, tz: tzinfo | str, t: Translator) -> str:
    """«• 12:40–14:10 ПР Разработка баз данных · И-212-б» in the user's zone; «• 12:40 …» for
    an event that ends when it starts (one without DTEND or DURATION)."""
    name = lesson_name(lesson)
    if len(name) > LESSON_NAME_LIMIT:
        name = name[: LESSON_NAME_LIMIT - 1] + "…"
    start, end = local_time(lesson.starts_at, tz), local_time(lesson.ends_at, tz)
    if end == start:
        return t("lesson-line-start", start=start, lesson=name)
    return t("lesson-line", start=start, end=end, lesson=name)


def _lesson_lines(data: TodayData, t: Translator, shown: int) -> list[str]:
    """The heading and the first `shown` lessons, then «…и ещё N» for the rest."""
    if not data.has_schedule:
        return []
    if not data.lessons:
        return [t("today-lessons-none")]
    zone = data.local_now.tzinfo or ZoneInfo("UTC")
    head = t("today-lessons-week", week=data.week_label) if data.week_label else t("today-lessons")
    listed = data.lessons[:shown]
    lines = [head, *(lesson_line(lesson, zone, t) for lesson in listed)]
    if len(data.lessons) > len(listed):
        lines.append(t("list-more", count=len(data.lessons) - len(listed)))
    return lines


def _within_limit(data: TodayData, render: Callable[[int, int], str]) -> str:
    """`render(reminders, lessons)` showing as many of each as fit TEXT_LIMIT: past it, the
    reminder list is cut from its end first, then the lesson list, each closed with «…и ещё N».
    Everything else in the message stays whole."""
    reminders = min(len(data.reminders), DAY_REMINDERS_SHOWN)
    lessons = min(len(data.lessons), DAY_LESSONS_SHOWN)
    text = render(reminders, lessons)
    while utf16_len(text) > TEXT_LIMIT and reminders + lessons > 0:
        if reminders > 0:
            reminders -= 1
        else:
            lessons -= 1
        text = render(reminders, lessons)
    return text


def streak_line(streak: Streak, t: Translator) -> str:
    """«🔥 Лучшая серия: «Спорт» — 5 дней» or «— 3 недели» for a weekly goal."""
    key = "today-streak" if streak.unit == "days" else "today-streak-weeks"
    return t(key, name=streak.name, count=streak.length)


def _rates_line(rates: Rates, currency: str, t: Translator) -> str:
    """«💵 84,20 ₽ · 💶 96,67 ₽», and the user's own currency when the bank quotes it."""
    usd = format_number(rates.usd.value, t.lang)
    eur = format_number(rates.eur.value, t.lang)
    own = rates.currencies.get(currency)
    if own is None or currency in ("USD", "EUR"):
        return t("today-rates", usd=usd, eur=eur)
    value = format_number(own.value, t.lang, _rate_digits(own.value))
    return t("today-rates-own", usd=usd, eur=eur, code=currency, own=value)


def _money_today(data: TodayData, t: Translator) -> list[str]:
    """«💰 Сегодня: 650 ₽ · октябрь: 12 400 ₽ из 30 000 ₽», once the month has entries."""
    month = data.money
    if month is None or not month.count:
        return []
    values = {
        "today": money(data.spent_today, data.currency, t),
        "month": month_name(month.first, t),
        "spent": money(month.spent, data.currency, t),
    }
    if month.budget is None:
        return [t("today-money-plain", **values)]
    return [t("today-money", budget=money(month.budget, data.currency, t), **values)]


def _money_morning(data: TodayData, t: Translator) -> list[str]:
    """Yesterday's spending and what the budget leaves for each day; nothing without either."""
    month = data.money
    yesterday = money(data.spent_yesterday, data.currency, t)
    if month is None or month.budget is None or month.left is None:
        return [t("morning-money-plain", yesterday=yesterday)] if data.spent_yesterday else []
    if month.left < 0:
        over = money(-month.left, data.currency, t)
        return [t("morning-money-over", yesterday=yesterday, over=over)]
    left = money(month.left, data.currency, t)
    per_day = money(month.per_day or 0, data.currency, t)
    return [t("morning-money", yesterday=yesterday, left=left, per_day=per_day)]


def _way(temperature: float | None, chance: int | None, t: Translator) -> str:
    """«+6°C», or «+6°C, 💧 70 %» when rain or snow is likely on the way."""
    if chance is None:
        return temp(temperature)
    return t("classes-temp-chance", temp=temp(temperature), chance=chance)


def _classes_lines(data: TodayData, t: Translator) -> list[str]:
    """The weather on the way to today's classes and back: «🎓 На пары (09:00): +3°C · после пар
    (16:20): +6°C, 💧 70 %». Once the first class has begun, or without the forecast's hour of
    its start, only the way back; nothing once the last class is over or without the hour of its
    end. «Now» is the moment the day was gathered at."""
    span = digest.classes_span(data)
    now = data.local_now
    if span is None or now >= span[1]:
        return []
    way = digest.classes_weather(data)
    if way is None:
        return []
    start, _ = span
    back = _way(way.end_temp, way.end_chance, t)
    finish = way.end.strftime("%H:%M")
    if now >= start or way.start_temp is None:
        return [t("classes-weather-after", end=finish, end_weather=back)]
    there = _way(way.start_temp, way.start_chance, t)
    return [
        t(
            "classes-weather",
            start=way.start.strftime("%H:%M"),
            start_weather=there,
            end=finish,
            end_weather=back,
        )
    ]


def _tomorrow_lines(data: TodayData, t: Translator) -> list[str]:
    """«Завтра: ☁️ +2…+7°C, 💧 80 %»: tomorrow's weather in the evening of the user's day, when
    the forecast has that day (digest.tomorrow_weather)."""
    day = digest.tomorrow_weather(data)
    if day is None:
        return []
    emoji, _ = describe_weather(day.code)
    values = {"emoji": emoji, "range": temp_range(day.tmin, day.tmax)}
    if _chance_shown(day.precip_chance):
        return [t("today-tomorrow-chance", chance=day.precip_chance, **values)]
    return [t("today-tomorrow", **values)]


def _pinned_line(note: NoteView, t: Translator) -> str:
    """«📌 Пароль от wifi: hunter2»; a checklist with its progress, «📌 Покупки ✅ 2/5»."""
    text = preview(note.text, PINNED_PREVIEW)
    if note.total:
        text = t("note-progress", text=text, done=note.done, total=note.total)
    return t("today-pinned", text=text)


def today_text(data: TodayData, name: str, t: Translator) -> str:
    """«Мой день»: the weather now with the first tip, the way to the classes, tomorrow in the
    evening and the data's source; the day's reminders, classes, habits and money; the notes with
    the pinned ones; the rates."""
    return _within_limit(data, lambda shown, lessons: _today(data, name, t, shown, lessons))


def _today(data: TodayData, name: str, t: Translator, shown: int, lessons: int) -> str:
    day = data.local_now.date()
    lines = [
        t("today-title", part=data.part_of_day, name=name),
        t("today-date", date=format_day(day, t.lang), weekday=format_weekday(day, t.lang)),
        "",
    ]
    if data.weather is not None:
        lines.append(_now_line(data.weather, t))
        lines += tip_lines(data.weather.tips[:1], t)
        lines += _classes_lines(data, t)
        lines += _tomorrow_lines(data, t)
        # Right under the weather: Open-Meteo's licence asks for the source next to the data.
        lines.append(t("weather-credit"))
    else:
        lines.append(t("today-weather-unavailable"))
    lines += ["", t("today-reminders", count=len(data.reminders))]
    lines += _reminder_lines(data, t, shown)
    lines += _lesson_lines(data, t, lessons)
    if data.habits_total:
        lines.append(t("today-habits", done=data.habits_done, total=data.habits_total))
    else:
        lines.append(t("today-habits-none"))
    if data.best_streak is not None:
        lines.append(streak_line(data.best_streak, t))
    lines += _money_today(data, t)
    lines.append(t("today-notes", count=data.notes_count))
    lines += [_pinned_line(note, t) for note in data.pinned]
    if data.rates is not None:
        lines.append(_rates_line(data.rates, data.currency, t))
    return "\n".join(lines)


def _morning_weather_line(now: WeatherNow, t: Translator) -> str:
    """«☁️ Москва: +4°C, пасмурно · днём до +9°C»: now and the day's highest; the line of now
    alone when the forecast has no highest for today."""
    if now.tmax is None:
        return _now_line(now, t)
    return t("morning-weather", max=temp(now.tmax), **_now_values(now, t))


def morning_text(data: TodayData, name: str, t: Translator) -> str:
    """The morning digest: the weather now with the day's highest, every tip, the way to the
    classes and the data's source; the day's reminders and classes; habits, money and rates.
    Never tomorrow: the day has only begun."""
    return _within_limit(data, lambda shown, lessons: _morning(data, name, t, shown, lessons))


def _morning(data: TodayData, name: str, t: Translator, shown: int, lessons: int) -> str:
    day = data.local_now.date()
    lines = [
        t("morning-title", name=name),
        t("morning-date", date=format_day(day, t.lang), weekday=format_weekday(day, t.lang)),
        "",
    ]
    if data.weather is not None:
        lines.append(_morning_weather_line(data.weather, t))
        lines += tip_lines(data.weather.tips, t)
        lines += _classes_lines(data, t)
        lines.append(t("weather-credit"))
    else:
        lines.append(t("today-weather-unavailable"))
    lines += ["", t("morning-reminders", count=len(data.reminders))]
    lines += _reminder_lines(data, t, shown)
    lines += _lesson_lines(data, t, lessons)
    extra: list[str] = []
    if data.habits_total:
        extra.append(t("morning-habits", count=data.habits_total))
    if data.best_streak is not None:
        extra.append(streak_line(data.best_streak, t))
    extra += _money_morning(data, t)
    if data.rates is not None:
        extra.append(_rates_line(data.rates, data.currency, t))
    if extra:
        lines += ["", *extra]
    return "\n".join(lines)


def _arrow(change: float) -> str:
    if change > 0:
        return "▲"
    return "▼" if change < 0 else "•"


def _rate_digits(value: float) -> int:
    """Four digits for a rate under ten roubles (a tenge is 0,1631 ₽), two for the others."""
    return 4 if value < 10 else 2


def rates_text(rates: Rates, t: Translator, currency: str) -> str:
    """USD and EUR, and the user's own currency when the bank quotes it."""
    lines = [t("rates-title", date=format_day(rates.day, t.lang)), ""]
    shown = [("💵", "USD", rates.usd), ("💶", "EUR", rates.eur)]
    own = rates.currencies.get(currency)
    if own is not None and currency not in ("USD", "EUR"):
        shown.append(("💱", currency, own))
    for emoji, code, rate in shown:
        digits = _rate_digits(rate.value)
        change = round(rate.change, digits)
        lines.append(
            t(
                "rates-line",
                emoji=emoji,
                code=code,
                value=format_number(rate.value, t.lang, digits),
                arrow=_arrow(change),
                change=format_number(abs(change), t.lang, digits),
            )
        )
    lines += ["", t("rates-converter")]
    return "\n".join(lines)


def short_moment(moment: datetime, tz: str, lang: str, now: datetime | None = None) -> str:
    local = to_local(moment, tz)
    same_year = local.year == to_local(now or utcnow(), tz).year
    return str(
        format_datetime(local, "d MMM, HH:mm" if same_year else "d MMM y, HH:mm", locale=lang)
    )


def long_day(day: date, lang: str, current_year: int) -> str:
    if day.year == current_year:
        return format_day(day, lang)
    return str(format_date(day, "d MMMM y" if lang == "ru" else "MMMM d, y", locale=lang))


def day_label(day: date, today: date, t: Translator) -> str:
    offset = (day - today).days
    if offset == 0:
        return t("day-today")
    if offset == 1:
        return t("day-tomorrow")
    if offset == 2:
        return t("day-after-tomorrow")
    if day.year != today.year:
        return str(format_date(day, "EEE, d MMM y", locale=t.lang))
    return format_short_day(day, t.lang)


def card_text(parsed: Parsed, local_now: datetime, t: Translator) -> str:
    """The confirmation card: what was understood, before anything is created."""
    today = local_now.date()
    rule = parsed.rule(local_now)
    if rule is not None:
        wall = local_now.replace(tzinfo=None)
        first = next(d for d in local_days(rule, today) if datetime.combine(d, rule.clock) > wall)
        return t(
            "reminder-card-repeat",
            rule=describe(rule, t),
            text=parsed.text,
            first=f"{day_label(first, today, t)}, {rule.time_local}",
        )
    when = parsed.when(local_now)
    if when is None:
        raise ValueError("a card needs a time")
    return t(
        "reminder-card",
        when=day_label(when.date(), today, t),
        time=when.strftime("%H:%M"),
        text=parsed.text,
    )


def saved_text(reminder: Reminder, tz: str, local_now: datetime, t: Translator) -> str:
    rule = reminders.rule_of(reminder)
    if rule is not None:
        return t("reminder-saved-repeat", rule=describe(rule, t), text=reminder.text)
    local = to_local(reminder.due_at, tz)
    return t(
        "reminder-saved",
        date=long_day(local.date(), t.lang, local_now.year),
        time=local.strftime("%H:%M"),
        text=reminder.text,
    )


def lesson_name(lesson: Lesson) -> str:
    """«ЛК Разработка баз данных · А-16»: the type, the subject and the room when known."""
    name = f"{lesson.kind} {lesson.title}" if lesson.kind else lesson.title
    return f"{name} · {lesson.room}" if lesson.room else name


def lesson_alert_text(lesson: Lesson, minutes: int, t: Translator) -> str:
    return t("lesson-alert", minutes=minutes, lesson=lesson_name(lesson))


_SOURCE_ERRORS = ("forbidden_host", "unreachable", "too_large", "not_calendar")


def fit(lines: Sequence[str], tail: Sequence[str] = ()) -> str:
    """The lines, cut with «…» where they would pass TEXT_LIMIT, then the tail whole: a page
    line, a legend or the stale warning, which must stay however long the list is."""
    ending = "".join(f"\n{line}" for line in tail)
    room = TEXT_LIMIT - utf16_len(ending)
    text = "\n".join(lines)
    if utf16_len(text) <= room:
        return text + ending
    kept: list[str] = []
    size = 0
    for line in lines:
        if size + utf16_len(line) + 1 > room - 2:
            break
        kept.append(line)
        size += utf16_len(line) + 1
    return "\n".join([*kept, "…"]) + ending


def day_title(day: date, today: date, t: Translator) -> str:
    """«Сегодня · понедельник, 28 сентября», or «среда, 30 сентября» further away."""
    full = f"{format_weekday(day, t.lang)}, {format_day(day, t.lang)}"
    word = {0: "day-today", 1: "day-tomorrow", -1: "day-yesterday"}.get((day - today).days)
    return f"{t(word)} · {full}" if word else full


def _stale_line(stale_since: date | None, t: Translator) -> list[str]:
    if stale_since is None:
        return []
    return ["", t("schedule-stale", date=format_day(stale_since, t.lang))]


def schedule_day_text(
    day: date,
    today: date,
    lessons: list[Lesson],
    week: str | None,
    tz: str,
    t: Translator,
    stale_since: date | None = None,
) -> str:
    title = day_title(day, today, t)
    head = t("schedule-day-week", day=title, week=week) if week else t("schedule-day", day=title)
    body = [lesson_line(lesson, tz, t) for lesson in lessons] or [t("schedule-free")]
    return fit([head, "", *body], _stale_line(stale_since, t))


def schedule_week_text(
    monday: date,
    lessons: list[Lesson],
    week: str | None,
    tz: str,
    t: Translator,
    stale_since: date | None = None,
) -> str:
    span = f"{format_day(monday, t.lang)} – {format_day(monday + timedelta(days=6), t.lang)}"
    lines = [
        t("schedule-week-label", week=week, range=span) if week else t("schedule-week", range=span)
    ]
    days: dict[date, list[Lesson]] = {}
    for lesson in lessons:
        days.setdefault(to_local(lesson.starts_at, tz).date(), []).append(lesson)
    if not days:
        lines += ["", t("schedule-free")]
    for day in sorted(days):
        lines += [
            "",
            format_short_day(day, t.lang),
            *(lesson_line(item, tz, t) for item in days[day]),
        ]
    return fit(lines, _stale_line(stale_since, t))


def schedule_source_text(source: ScheduleSource, tz: str, now: datetime, t: Translator) -> str:
    title = source.title or t("schedule-source-untitled")
    lines = [t("schedule-source-title"), "", t(f"schedule-source-{source.kind.value}", title=title)]
    if source.ok_at is not None:
        lines.append(t("schedule-updated", when=short_moment(source.ok_at, tz, t.lang, now)))
    if source.error:
        lines.append(t("schedule-failed"))
    minutes = source.lesson_reminder_minutes
    lines.append(t("schedule-alerts-on", minutes=minutes) if minutes else t("schedule-alerts-off"))
    return "\n".join(lines)


def schedule_error_text(reason: str, t: Translator) -> str:
    return t(f"schedule-error-{reason if reason in _SOURCE_ERRORS else 'unreachable'}")
