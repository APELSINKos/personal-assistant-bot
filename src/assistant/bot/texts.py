"""Service data → message text. Pure functions without I/O."""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

from babel.dates import format_date, format_datetime

from assistant.core.clients.cbr import Rates
from assistant.core.i18n import Translator, format_day, format_number, format_weekday
from assistant.core.services.digest import TodayData
from assistant.core.services.weather import Tip, WeatherNow, describe
from assistant.core.timeutil import to_local, utcnow

NO_VALUE = "—"
# Telegram messages are capped at 4096 characters; with up to 20 pending reminders at
# 200 characters each, rendering all of them could blow that limit on its own. Cap the
# rendered list and summarise the rest in one line instead.
DAY_REMINDERS_SHOWN = 10


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


def _now_line(weather: WeatherNow, t: Translator) -> str:
    emoji, key = describe(weather.code)
    return t(
        "weather-now",
        emoji=emoji,
        city=weather.city,
        temp=temp(weather.temperature),
        description=t(key),
    )


def weather_text(now: WeatherNow, t: Translator) -> str:
    wind = NO_VALUE if now.wind is None else str(round(now.wind))
    return "\n".join(
        [
            _now_line(now, t),
            t("weather-feels", feels=temp(now.feels_like), wind=wind),
            t("weather-range", range=temp_range(now.tmin, now.tmax)),
            "",
            *tip_lines(now.tips, t),
        ]
    )


def _reminder_lines(data: TodayData, t: Translator) -> list[str]:
    zone = data.local_now.tzinfo or ZoneInfo("UTC")
    shown = data.reminders[:DAY_REMINDERS_SHOWN]
    lines = [t("list-item-time", time=local_time(r.due_at, zone), text=r.text) for r in shown]
    hidden = len(data.reminders) - len(shown)
    if hidden > 0:
        lines.append(t("list-more", count=hidden))
    return lines


def _rates_line(rates: Rates, t: Translator) -> str:
    return t(
        "today-rates",
        usd=format_number(rates.usd.value, t.lang),
        eur=format_number(rates.eur.value, t.lang),
    )


def today_text(data: TodayData, name: str, t: Translator) -> str:
    day = data.local_now.date()
    lines = [
        t("today-title", part=data.part_of_day, name=name),
        t("today-date", date=format_day(day, t.lang), weekday=format_weekday(day, t.lang)),
        "",
    ]
    if data.weather is not None:
        lines.append(_now_line(data.weather, t))
        lines += tip_lines(data.weather.tips[:1], t)
    else:
        lines.append(t("today-weather-unavailable"))
    lines += ["", t("today-reminders", count=len(data.reminders)), *_reminder_lines(data, t)]
    if data.habits_total:
        lines.append(t("today-habits", done=data.habits_done, total=data.habits_total))
    else:
        lines.append(t("today-habits-none"))
    if data.best_streak is not None:
        lines.append(t("today-streak", name=data.best_streak[0], count=data.best_streak[1]))
    lines.append(t("today-notes", count=data.notes_count))
    if data.rates is not None:
        lines.append(_rates_line(data.rates, t))
    return "\n".join(lines)


def morning_text(data: TodayData, name: str, t: Translator) -> str:
    day = data.local_now.date()
    lines = [
        t("morning-title", name=name),
        t("morning-date", date=format_day(day, t.lang), weekday=format_weekday(day, t.lang)),
        "",
    ]
    if data.weather is not None:
        lines.append(
            t(
                "morning-weather",
                city=data.weather.city,
                range=temp_range(data.weather.tmin, data.weather.tmax),
            )
        )
        lines += tip_lines(data.weather.tips, t)
    else:
        lines.append(t("today-weather-unavailable"))
    lines += ["", t("morning-reminders", count=len(data.reminders)), *_reminder_lines(data, t)]
    extra: list[str] = []
    if data.habits_total:
        extra.append(t("morning-habits", count=data.habits_total))
    if data.best_streak is not None:
        extra.append(t("today-streak", name=data.best_streak[0], count=data.best_streak[1]))
    if data.rates is not None:
        extra.append(_rates_line(data.rates, t))
    if extra:
        lines += ["", *extra]
    return "\n".join(lines)


def _arrow(change: float) -> str:
    if change > 0:
        return "▲"
    return "▼" if change < 0 else "•"


def rates_text(rates: Rates, t: Translator) -> str:
    lines = [t("rates-title", date=format_day(rates.day, t.lang)), ""]
    for emoji, code, rate in (("💵", "USD", rates.usd), ("💶", "EUR", rates.eur)):
        change = round(rate.change, 2)
        lines.append(
            t(
                "rates-line",
                emoji=emoji,
                code=code,
                value=format_number(rate.value, t.lang),
                arrow=_arrow(change),
                change=format_number(abs(change), t.lang),
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
