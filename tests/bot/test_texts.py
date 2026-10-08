from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from assistant.bot import texts
from assistant.bot.routers.habits import habits_view
from assistant.bot.routers.notes import notes_view
from assistant.bot.routers.reminders import reminders_view
from assistant.core.clients.cbr import Rate, Rates
from assistant.core.i18n import Translator, format_day, translator
from assistant.core.models import Habit, Lesson, Reminder, Repeat, User
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import HabitStats, Streak
from assistant.core.services.money_month import Month
from assistant.core.services.notes import Item, NoteView
from assistant.core.services.weather import Forecast, Tip, WeatherNow
from assistant.core.services.weather import parse as parse_forecast
from tests.stubs import FORECAST_NOW, forecast_payload

RU, EN = translator("ru"), translator("en")
MSK = ZoneInfo("Europe/Moscow")
BUDGET = 3900  # what the bot keeps a message within, a margin under Telegram's 4096
NBSP = "\u00a0"


def utf16(text: str) -> int:
    """A message's length as Telegram counts it: a character outside the BMP is two."""
    return len(text.encode("utf-16-le")) // 2


WEATHER = WeatherNow(
    city="Москва",
    temperature=9.6,
    feels_like=7.2,
    wind=3.4,
    code=1,
    tmin=5.8,
    tmax=13.2,
    tips=[Tip("tip-bike")],
)
RATES = Rates(date(2026, 9, 28), Rate(84.1975, -0.3118), Rate(96.6671, 0.0))


def habit_today(mark: bool | None) -> HabitStats:
    """A daily habit with today's mark: done (True), skipped (False) or none yet (None)."""
    return HabitStats(
        habit=Habit(name="Спорт", weekly_goal=7, emoji="🎯"),
        today=date(2026, 9, 28),
        done_today=mark,
        streak=5,
        done_days=5,
        total_days=5,
        last_days=(True,) * 8 + (mark,),
        record=5,
        percent=100,
        week_done=1,
        week_goal=7,
        week="1......",
    )


def day_data(**changes: object) -> TodayData:
    values: dict[str, object] = {
        "local_now": datetime(2026, 9, 28, 8, 0, tzinfo=MSK),
        "part_of_day": "morning",
        "weather": WEATHER,
        "reminders": [Reminder(text="встреча", due_at=datetime(2026, 9, 28, 9, 30, tzinfo=UTC))],
        "habits": [habit_today(True), habit_today(None), habit_today(None)],
        "habits_done": 1,
        "habits_total": 3,
        "notes_count": 4,
        "rates": RATES,
        "best_streak": Streak("Спорт", 5, "days"),
    }
    values.update(changes)
    return TodayData(**values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(14.2, "+14°C"), (-3.7, "-4°C"), (0.2, "0°C"), (-0.4, "0°C"), (None, "—")],
)
def test_temp(value: float | None, expected: str) -> None:
    assert texts.temp(value) == expected


def test_weather_text() -> None:
    assert texts.weather_text(WEATHER, RU) == (
        "🌤 Москва: +10°C, малооблачно\n"
        "Ощущается как +7°C, ветер 3 м/с\n"
        "Сегодня: +6…+13°C\n"
        "\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "\n"
        "Данные о погоде: open-meteo.com"
    )
    assert texts.weather_text(WEATHER, EN).endswith("\n\nWeather data: open-meteo.com")


def test_weather_at_night_shows_the_moon_for_a_clear_sky() -> None:
    night = replace(WEATHER, is_day=False)
    assert texts.weather_text(night, RU).startswith("🌙 Москва: +10°C, малооблачно\n")
    cloudy = replace(night, code=3)
    assert texts.weather_text(cloudy, RU).startswith("☁️ Москва: +10°C, пасмурно\n")
    assert "🌙 Москва: +10°C" in texts.today_text(day_data(weather=night), "Alex", RU)


# The stub forecast of Moscow, asked for at FORECAST_NOW: 10:00 there.
FORECAST = parse_forecast(forecast_payload(), "Москва")


def test_hours_text() -> None:
    assert texts.hours_text(FORECAST, FORECAST_NOW, "Europe/Moscow", RU) == (
        "🕐 Москва — по часам\n"
        "\n"
        "11:00 🌤 +11°C\n"
        "12:00 🌤 +12°C\n"
        "13:00 🌤 +13°C\n"
        "14:00 🌤 +13°C\n"
        "15:00 🌤 +13°C\n"
        "16:00 🌤 +13°C\n"
        "17:00 🌤 +12°C\n"
        "18:00 🌤 +12°C\n"
        "19:00 🌙 +11°C\n"
        "20:00 🌙 +10°C\n"
        "21:00 🌙 +9°C\n"
        "22:00 🌙 +8°C\n"
        "\n"
        "Данные о погоде: open-meteo.com"
    )


def test_hours_across_midnight() -> None:
    evening = datetime(2026, 9, 28, 20, 30, tzinfo=MSK)
    lines = texts.hours_text(FORECAST, evening, "Europe/Moscow", RU).split("\n")
    assert lines[2:7] == [
        "21:00 🌙 +9°C",
        "22:00 🌙 +8°C",
        "23:00 🌙 +8°C",
        "Завтра, 29 сентября",
        "00:00 🌙 +7°C",
    ]
    assert lines[-3:] == ["08:00 🌤 +8°C", "", "Данные о погоде: open-meteo.com"]
    # The date line comes first when every hour shown is tomorrow's.
    late = datetime(2026, 9, 28, 23, 30, tzinfo=MSK)
    lines = texts.hours_text(FORECAST, late, "Europe/Moscow", EN).split("\n")
    assert lines[:4] == ["🕐 Москва — hourly", "", "Tomorrow, September 29", "00:00 🌙 +7°C"]
    assert len(lines) == 4 + 11 + 2  # twelve hours


def test_hours_at_the_end_of_the_forecast() -> None:
    last = datetime(2026, 10, 4, 20, 30, tzinfo=MSK)  # three hours of the week are left
    lines = texts.hours_text(FORECAST, last, "Europe/Moscow", RU).split("\n")
    assert lines[2:] == [
        "21:00 🌙 +9°C",
        "22:00 🌙 +8°C",
        "23:00 🌙 +8°C",
        "",
        "Данные о погоде: open-meteo.com",
    ]
    gone = datetime(2026, 10, 4, 23, 30, tzinfo=MSK)
    lines = texts.hours_text(FORECAST, gone, "Europe/Moscow", RU).split("\n")
    assert lines[2:] == ["Почасового прогноза сейчас нет.", "", "Данные о погоде: open-meteo.com"]
    english = texts.hours_text(FORECAST, gone, "Europe/Moscow", EN)
    assert english.split("\n")[2] == "No hourly forecast right now."


def test_a_day_after_hours_missing_from_the_forecast_is_named_by_its_date() -> None:
    data = forecast_payload()
    data["hourly"]["temperature_2m"][14:48] = [None] * 34  # from 14:00 to the end of tomorrow
    forecast = parse_forecast(data, "Москва")
    lines = texts.hours_text(forecast, FORECAST_NOW, "Europe/Moscow", RU).split("\n")
    assert lines[2:7] == [
        "11:00 🌤 +11°C",
        "12:00 🌤 +12°C",
        "13:00 🌤 +13°C",
        "30 сентября",
        "00:00 🌙 +7°C",
    ]


def test_a_chance_of_rain_from_20_percent() -> None:
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][11:14] = [19, 20, 40]  # 11:00 to 13:00
    data["hourly"]["weather_code"][13] = 61
    data["daily"]["precipitation_probability_max"][:3] = [19, 20, 80]
    data["daily"]["weather_code"][2] = 63
    forecast = parse_forecast(data, "Москва")
    hours = texts.hours_text(forecast, FORECAST_NOW, "Europe/Moscow", RU).split("\n")
    assert hours[2:5] == ["11:00 🌤 +11°C", "12:00 🌤 +12°C 💧 20 %", "13:00 🌧 +13°C 💧 40 %"]
    english = texts.hours_text(forecast, FORECAST_NOW, "Europe/Moscow", EN).split("\n")
    assert english[4] == "13:00 🌧 +13°C 💧 40%"
    week = texts.week_text(forecast, FORECAST_NOW, RU).split("\n")
    assert week[2:5] == [
        "Сегодня 🌤 +6…+13°C",
        "Завтра 🌤 +6…+13°C 💧 20 %",
        "ср, 30 сент. 🌧 +6…+13°C 💧 80 %",
    ]
    assert texts.week_text(forecast, FORECAST_NOW, EN).split("\n")[4] == (
        "Wed, 30 Sep 🌧 +6…+13°C 💧 80%"
    )


def test_hours_on_the_clock_of_another_zone_say_so() -> None:
    omsk = parse_forecast(forecast_payload(zone="Asia/Omsk"), "Омск")
    lines = texts.hours_text(omsk, FORECAST_NOW, "Europe/Moscow", RU).split("\n")
    # Omsk's hours: 13:00 there is 10:00 in Moscow.
    assert lines[:3] == ["🕐 Омск — по часам (местное время)", "", "14:00 🌤 +13°C"]
    english = texts.hours_text(omsk, FORECAST_NOW, "Europe/Moscow", EN)
    assert english.startswith("🕐 Омск — hourly (local time)\n")
    # Another zone on the same clock is not another time.
    istanbul = parse_forecast(forecast_payload(zone="Europe/Istanbul"), "Стамбул")
    text = texts.hours_text(istanbul, FORECAST_NOW, "Europe/Moscow", RU)
    assert text.startswith("🕐 Стамбул — по часам\n")


def test_the_clocks_are_compared_at_the_moment_itself() -> None:
    # At 01:30 UTC on 25 October Berlin's clocks are half an hour back on UTC+1, which Lagos
    # keeps all year. Berlin's offset of 01:30 taken as its wall time would still be +2.
    after = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    berlin = parse_forecast(forecast_payload(after, "Europe/Berlin"), "Берлин")
    assert texts.hours_text(berlin, after, "Africa/Lagos", RU).startswith("🕐 Берлин — по часам\n")
    before = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    berlin = parse_forecast(forecast_payload(before, "Europe/Berlin"), "Берлин")
    title = texts.hours_text(berlin, before, "Africa/Lagos", RU).split("\n")[0]
    assert title == "🕐 Берлин — по часам (местное время)"


def test_week_text() -> None:
    assert texts.week_text(FORECAST, FORECAST_NOW, RU) == (
        "📅 Москва — 7 дней\n"
        "\n"
        "Сегодня 🌤 +6…+13°C\n"
        "Завтра 🌤 +6…+13°C\n"
        "ср, 30 сент. 🌤 +6…+13°C\n"
        "чт, 1 окт. 🌤 +6…+13°C\n"
        "пт, 2 окт. 🌤 +6…+13°C\n"
        "сб, 3 окт. 🌤 +6…+13°C\n"
        "вс, 4 окт. 🌤 +6…+13°C\n"
        "\n"
        "Данные о погоде: open-meteo.com"
    )
    assert texts.week_text(FORECAST, FORECAST_NOW, EN).split("\n")[:5] == [
        "📅 Москва — 7 days",
        "",
        "Today 🌤 +6…+13°C",
        "Tomorrow 🌤 +6…+13°C",
        "Wed, 30 Sep 🌤 +6…+13°C",
    ]


def test_the_week_just_after_midnight_has_six_days() -> None:
    # The answer kept since 23:50 still starts with the day before.
    asked = datetime(2026, 9, 27, 23, 50, tzinfo=MSK)
    forecast = parse_forecast(forecast_payload(asked), "Москва")
    text = texts.week_text(forecast, datetime(2026, 9, 28, 0, 5, tzinfo=MSK), RU)
    assert text.split("\n")[2:-2] == [
        "Сегодня 🌤 +6…+13°C",
        "Завтра 🌤 +6…+13°C",
        "ср, 30 сент. 🌤 +6…+13°C",
        "чт, 1 окт. 🌤 +6…+13°C",
        "пт, 2 окт. 🌤 +6…+13°C",
        "сб, 3 окт. 🌤 +6…+13°C",
    ]


def test_a_week_without_days_says_so() -> None:
    # A day without its maximum is left out of the forecast, and here that is every day.
    data = forecast_payload()
    data["daily"]["temperature_2m_max"] = [None] * 7
    forecast = parse_forecast(data, "Москва")
    assert texts.week_text(forecast, FORECAST_NOW, RU).split("\n") == [
        "📅 Москва — 7 дней",
        "",
        "Прогноза на неделю сейчас нет.",
        "",
        "Данные о погоде: open-meteo.com",
    ]
    english = texts.week_text(forecast, FORECAST_NOW, EN)
    assert english.split("\n")[2] == "No forecast for the week right now."


def test_today_text_full() -> None:
    assert texts.today_text(day_data(), "Alex", RU) == (
        "🌅 Доброе утро, Alex!\n"
        "📅 Сегодня, 28 сентября, понедельник\n"
        "\n"
        "🌤 Москва: +10°C, малооблачно\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "Данные о погоде: open-meteo.com\n"
        "\n"
        "📌 На сегодня 1 напоминание:\n"
        "• 12:30 — встреча\n"
        "🎯 Привычки: 1 из 3\n"
        "🔥 Лучшая серия: «Спорт» — 5 дней\n"
        "📝 Заметок: 4\n"
        "💵 84,20 ₽ · 💶 96,67 ₽"
    )


def test_today_text_when_everything_is_missing() -> None:
    data = day_data(
        part_of_day="night",
        weather=None,
        reminders=[],
        habits_done=0,
        habits_total=0,
        notes_count=0,
        rates=None,
        best_streak=None,
    )
    assert texts.today_text(data, "Alex", RU) == (
        "🌙 Доброй ночи, Alex!\n"
        "📅 Сегодня, 28 сентября, понедельник\n"
        "\n"
        "🌤 Погода временно недоступна\n"
        "\n"
        "📌 На сегодня напоминаний нет\n"
        "🎯 Привычек пока нет\n"
        "📝 Заметок: 0"
    )


def test_today_text_english_plurals() -> None:
    text = texts.today_text(day_data(best_streak=Streak("Run", 1, "days")), "Alex", EN)
    assert "📅 Today, Monday, September 28" in text
    assert "📌 1 reminder for today:" in text
    assert "🔥 Best streak: “Run” — 1 day" in text


@pytest.mark.parametrize(
    ("count", "russian", "english"),
    [(1, "1 неделя", "1 week"), (3, "3 недели", "3 weeks"), (5, "5 недель", "5 weeks")],
)
def test_the_best_streak_of_a_weekly_habit_is_counted_in_weeks(
    count: int, russian: str, english: str
) -> None:
    data = day_data(best_streak=Streak("Бег", count, "weeks"))
    for render in (texts.today_text, texts.morning_text):
        assert f"🔥 Лучшая серия: «Бег» — {russian}\n" in render(data, "Alex", RU)
        assert f"🔥 Best streak: “Бег” — {english}\n" in render(data, "Alex", EN)


def test_morning_text() -> None:
    assert texts.morning_text(day_data(), "Alex", RU) == (
        "☀️ Доброе утро, Alex!\n"
        "📅 28 сентября, понедельник\n"
        "\n"
        "🌤 Москва: +10°C, малооблачно · днём до +13°C\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "Данные о погоде: open-meteo.com\n"
        "\n"
        "📌 Сегодня:\n"
        "• 12:30 — встреча\n"
        "\n"
        "🎯 Привычек на сегодня: 2 — не забудь отметить\n"  # one of the three is marked
        "🔥 Лучшая серия: «Спорт» — 5 дней\n"
        "💵 84,20 ₽ · 💶 96,67 ₽"
    )


def test_morning_text_minimal() -> None:
    data = day_data(
        weather=None, reminders=[], habits=[], habits_total=0, best_streak=None, rates=None
    )
    assert texts.morning_text(data, "Alex", RU) == (
        "☀️ Доброе утро, Alex!\n"
        "📅 28 сентября, понедельник\n"
        "\n"
        "🌤 Погода временно недоступна\n"
        "\n"
        "📌 На сегодня напоминаний нет"
    )


def habits_line(marks: Sequence[bool | None], t: Translator) -> list[str]:
    """The digest's line of habits, if any, for habits with these marks today."""
    habits = [habit_today(mark) for mark in marks]
    data = day_data(habits=habits, habits_done=marks.count(True), habits_total=len(marks))
    return [line for line in texts.morning_text(data, "Alex", t).split("\n") if "🎯" in line]


def test_the_digest_counts_only_the_habits_not_yet_marked() -> None:
    # «Спорт» marked just after midnight, or in the app at 07:05: one habit of the two to go.
    assert habits_line([True, None], RU) == ["🎯 Привычек на сегодня: 1 — не забудь отметить"]
    assert habits_line([True, None], EN) == ["🎯 Habits for today: 1 — don't forget to mark it"]
    assert habits_line([None, False, None], RU) == [
        "🎯 Привычек на сегодня: 2 — не забудь отметить"
    ]
    assert habits_line([None, False, None], EN) == [
        "🎯 Habits for today: 2 — don't forget to mark them"
    ]
    # Done or skipped, every habit has its mark: nothing to remind of.
    assert habits_line([True, False], RU) == habits_line([True, False], EN) == []


def test_the_digest_tells_the_weather_now_and_the_days_highest() -> None:
    english = texts.morning_text(day_data(), "Alex", EN).split("\n")
    assert english[3] == "🌤 Москва: +10°C, partly cloudy · up to +13°C today"
    night = replace(WEATHER, code=0, is_day=False, temperature=-3.6, tmax=1.2)
    lines = texts.morning_text(day_data(weather=night), "Alex", RU).split("\n")
    assert lines[3] == "🌙 Москва: -4°C, ясно · днём до +1°C"
    # Without today's highest the line of now alone.
    plain = replace(WEATHER, tmax=None)
    assert texts.morning_text(day_data(weather=plain), "Alex", RU).split("\n")[3] == (
        "🌤 Москва: +10°C, малооблачно"
    )


def at(clock: str) -> datetime:
    """28 September at this time of Moscow."""
    return datetime.combine(date(2026, 9, 28), time.fromisoformat(clock), MSK)


def lesson_at(
    start: str, end: str, title: str = "Физика", kind: str = "ЛК", room: str = "А-16"
) -> Lesson:
    """A lesson of 28 September between two times of Moscow, in UTC as the stored ones are."""
    return Lesson(
        uid=f"{start}-{end}",
        starts_at=at(start).astimezone(UTC),
        ends_at=at(end).astimezone(UTC),
        title=title,
        kind=kind,
        room=room,
    )


def forecast_with(chances: dict[int, int], *, tomorrow: int = 0) -> Forecast:
    """The stub forecast of Moscow with these chances of rain at today's labels (17 tells of
    16:00–17:00) and, with a chance tomorrow, rain tomorrow."""
    data = forecast_payload()
    for label, chance in chances.items():
        data["hourly"]["precipitation_probability"][label] = chance
    if tomorrow:
        data["daily"]["weather_code"][1] = 61
        data["daily"]["precipitation_probability_max"][1] = tomorrow
    return parse_forecast(data, "Москва")


# Classes from 09:00 to 16:20 in Moscow, and rain likely on the way home: 16:20–17:00.
CLASSES = [
    lesson_at("09:00", "10:30"),
    lesson_at("14:50", "16:20", "Разработка баз данных", "ПР", "И-212-б"),
]
RAIN_HOME = forecast_with({17: 70}, tomorrow=80)
WAY = "🎓 На пары (09:00): +9°C · после пар (16:20): +13°C, 💧 70 %"
WAY_BACK = "🎓 После пар (16:20): +13°C, 💧 70 %"


def classes_day(
    clock: str, forecast: Forecast = RAIN_HOME, lessons: list[Lesson] = CLASSES
) -> TodayData:
    return day_data(local_now=at(clock), forecast=forecast, has_schedule=True, lessons=lessons)


def way_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith(("🎓 На пары", "🎓 После пар"))]


@pytest.mark.parametrize(
    ("clock", "line"),
    [
        ("08:00", WAY),
        ("08:59", WAY),
        ("09:00", WAY_BACK),  # the first class has begun: the way back alone
        ("16:19", WAY_BACK),
        ("16:20", None),  # the last one is over
        ("23:00", None),
    ],
)
def test_the_way_to_the_classes_and_back(clock: str, line: str | None) -> None:
    data = classes_day(clock)
    for render in (texts.today_text, texts.morning_text):
        assert way_lines(render(data, "Alex", RU)) == ([line] if line else [])


def test_the_way_tells_of_rain_from_30_percent_and_in_english() -> None:
    forecast = forecast_with({9: 30, 17: 70})  # 08:00–09:00 and 16:00–17:00
    assert way_lines(texts.today_text(classes_day("08:00", forecast), "Alex", RU)) == [
        "🎓 На пары (09:00): +9°C, 💧 30 % · после пар (16:20): +13°C, 💧 70 %"
    ]
    english = texts.morning_text(classes_day("08:00", forecast), "Alex", EN).split("\n")
    assert "🎓 To classes (09:00): +9°C, 💧 30% · after (16:20): +13°C, 💧 70%" in english
    later = texts.today_text(classes_day("10:00", forecast), "Alex", EN).split("\n")
    assert "🎓 After classes (16:20): +13°C, 💧 70%" in later
    dry = forecast_with({9: 29, 17: 29})
    assert way_lines(texts.today_text(classes_day("08:00", dry), "Alex", RU)) == [
        "🎓 На пары (09:00): +9°C · после пар (16:20): +13°C"
    ]


def test_the_way_without_the_forecasts_hour_of_its_start_or_its_end() -> None:
    data = forecast_payload()
    data["hourly"]["precipitation_probability"][17] = 70
    data["hourly"]["temperature_2m"][9] = None  # no hour from 09:00: the way there is unknown
    no_start = parse_forecast(data, "Москва")
    assert way_lines(texts.today_text(classes_day("08:00", no_start), "Alex", RU)) == [WAY_BACK]
    data["hourly"]["temperature_2m"][16] = None  # nor the one 16:20 falls in: no line at all
    no_end = parse_forecast(data, "Москва")
    for render in (texts.today_text, texts.morning_text):
        assert way_lines(render(classes_day("08:00", no_end), "Alex", RU)) == []


def test_no_way_without_classes_or_the_forecast() -> None:
    assert way_lines(texts.today_text(classes_day("08:00", lessons=[]), "Alex", RU)) == []
    no_forecast = day_data(has_schedule=True, lessons=CLASSES)
    assert way_lines(texts.morning_text(no_forecast, "Alex", RU)) == []


def test_the_way_is_found_on_the_forecasts_clock_and_told_on_the_users() -> None:
    # A forecast three hours ahead of the user's clock: 09:00 in Moscow is its 12:00.
    omsk = parse_forecast(forecast_payload(zone="Asia/Omsk"), "Омск")
    assert way_lines(texts.today_text(classes_day("08:00", omsk), "Alex", RU)) == [
        "🎓 На пары (09:00): +12°C · после пар (16:20): +11°C"
    ]


def tomorrow_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith(("Завтра", "Tomorrow"))]


@pytest.mark.parametrize(
    ("clock", "shown"), [("00:00", False), ("16:59", False), ("17:00", True), ("23:59", True)]
)
def test_my_day_tells_of_tomorrow_in_the_evening(clock: str, shown: bool) -> None:
    data = day_data(local_now=at(clock), forecast=RAIN_HOME)
    lines = tomorrow_lines(texts.today_text(data, "Alex", RU))
    assert lines == (["Завтра: 🌧 +6…+13°C, 💧 80 %"] if shown else [])
    assert tomorrow_lines(texts.morning_text(data, "Alex", RU)) == []  # the digest never does


def test_tomorrow_tells_of_its_chance_from_20_percent() -> None:
    def tomorrow(forecast: Forecast, t: Translator) -> list[str]:
        data = day_data(local_now=at("18:00"), forecast=forecast)
        return tomorrow_lines(texts.today_text(data, "Alex", t))

    assert tomorrow(forecast_with({}), RU) == ["Завтра: 🌤 +6…+13°C"]
    assert tomorrow(forecast_with({}, tomorrow=19), RU) == ["Завтра: 🌧 +6…+13°C"]
    assert tomorrow(forecast_with({}, tomorrow=20), RU) == ["Завтра: 🌧 +6…+13°C, 💧 20 %"]
    assert tomorrow(forecast_with({}, tomorrow=20), EN) == ["Tomorrow: 🌧 +6…+13°C, 💧 20%"]
    # A forecast without tomorrow has no line.
    assert tomorrow(parse_forecast(forecast_payload(days=1), "Москва"), RU) == []


def note_view(text: str, checks: Sequence[bool] = ()) -> NoteView:
    moment = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)
    items = [Item(id=n, text=f"пункт {n}", done=done) for n, done in enumerate(checks, 1)]
    return NoteView(
        id=1, text=text, pinned_at=moment, created_at=moment, updated_at=moment, items=items
    )


PINNED = [
    note_view("Пароль от wifi:\nhunter2"),
    note_view("Покупки", [True, True, False, False, False]),
    note_view("Записать маму к врачу на следующей неделе, лучше утром"),
]


def test_my_day_shows_the_pinned_notes_under_their_count() -> None:
    lines = texts.today_text(day_data(pinned=PINNED), "Alex", RU).split("\n")
    notes = lines.index("📝 Заметок: 4")
    assert lines[notes + 1 :] == [
        "📌 Пароль от wifi: hunter2",
        "📌 Покупки ✅ 2/5",
        "📌 Записать маму к врачу на следующей неде…",  # 39 characters and «…»
        "💵 84,20 ₽ · 💶 96,67 ₽",
    ]
    english = texts.today_text(day_data(pinned=PINNED), "Alex", EN).split("\n")
    assert english[english.index("📝 Notes: 4") + 2] == "📌 Покупки ✅ 2/5"
    assert "Покупки" not in texts.morning_text(day_data(pinned=PINNED), "Alex", RU)


def test_my_day_in_the_evening_with_all_of_its_weather() -> None:
    data = day_data(
        local_now=at("17:30"),
        part_of_day="evening",
        forecast=forecast_with({20: 60}, tomorrow=80),  # 19:00–20:00
        has_schedule=True,
        lessons=[lesson_at("18:00", "19:30")],
        pinned=PINNED[:2],
    )
    assert texts.today_text(data, "Alex", RU) == (
        "🌆 Добрый вечер, Alex!\n"
        "📅 Сегодня, 28 сентября, понедельник\n"
        "\n"
        "🌤 Москва: +10°C, малооблачно\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "🎓 На пары (18:00): +12°C · после пар (19:30): +11°C, 💧 60 %\n"
        "Завтра: 🌧 +6…+13°C, 💧 80 %\n"
        "Данные о погоде: open-meteo.com\n"
        "\n"
        "📌 На сегодня 1 напоминание:\n"
        "• 12:30 — встреча\n"
        "🎓 Пары:\n"
        "• 18:00–19:30 ЛК Физика · А-16\n"
        "🎯 Привычки: 1 из 3\n"
        "🔥 Лучшая серия: «Спорт» — 5 дней\n"
        "📝 Заметок: 4\n"
        "📌 Пароль от wifi: hunter2\n"
        "📌 Покупки ✅ 2/5\n"
        "💵 84,20 ₽ · 💶 96,67 ₽"
    )
    english = texts.today_text(data, "Alex", EN).split("\n")
    assert english[5:8] == [
        "🎓 To classes (18:00): +12°C · after (19:30): +11°C, 💧 60%",
        "Tomorrow: 🌧 +6…+13°C, 💧 80%",
        "Weather data: open-meteo.com",
    ]


def test_the_digest_with_the_way_to_the_classes() -> None:
    assert texts.morning_text(classes_day("08:00"), "Alex", RU) == (
        "☀️ Доброе утро, Alex!\n"
        "📅 28 сентября, понедельник\n"
        "\n"
        "🌤 Москва: +10°C, малооблачно · днём до +13°C\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "🎓 На пары (09:00): +9°C · после пар (16:20): +13°C, 💧 70 %\n"
        "Данные о погоде: open-meteo.com\n"
        "\n"
        "📌 Сегодня:\n"
        "• 12:30 — встреча\n"
        "🎓 Пары:\n"
        "• 09:00–10:30 ЛК Физика · А-16\n"
        "• 14:50–16:20 ПР Разработка баз данных · И-212-б\n"
        "\n"
        "🎯 Привычек на сегодня: 2 — не забудь отметить\n"
        "🔥 Лучшая серия: «Спорт» — 5 дней\n"
        "💵 84,20 ₽ · 💶 96,67 ₽"
    )


def test_reminder_list_is_capped_within_the_telegram_message_limit() -> None:
    reminders = [
        Reminder(text="x" * 200, due_at=datetime(2026, 9, 28, 9, 30, tzinfo=UTC)) for _ in range(20)
    ]
    data = day_data(reminders=reminders)
    for render in (texts.today_text, texts.morning_text):
        text = render(data, "Alex", RU)
        assert len(text) <= 4096
        lines = text.splitlines()
        bullets = [line for line in lines if line.startswith("• ")]
        assert len(bullets) == 10
        overflow = lines.index("…и ещё 10")
        assert lines[overflow - 10 : overflow] == bullets


def test_rates_text() -> None:
    assert texts.rates_text(RATES, RU, "RUB") == (
        "💱 Курс ЦБ РФ на 28 сентября\n"
        "\n"
        "💵 USD: 84,20 ₽  ▼ 0,31\n"
        "💶 EUR: 96,67 ₽  • 0,00\n"
        "\n"
        "Конвертер 👇"
    )


def test_rates_text_adds_the_users_own_currency() -> None:
    rates = Rates(RATES.day, RATES.usd, RATES.eur, currencies={"KZT": Rate(0.1631, 0.0012)})
    assert texts.rates_text(rates, EN, "KZT").split("\n")[2:5] == [
        "💵 USD: 84.20 ₽  ▼ 0.31",
        "💶 EUR: 96.67 ₽  • 0.00",
        "💱 KZT: 0.1631 ₽  ▲ 0.0012",
    ]
    for currency in ("RUB", "USD", "GBP"):  # the rouble, a currency shown anyway, one not quoted
        assert len(texts.rates_text(rates, RU, currency).split("\n")) == 6


LESSON = Lesson(
    uid="75bb3b9e",
    starts_at=datetime(2026, 9, 28, 9, 40, tzinfo=UTC),
    ends_at=datetime(2026, 9, 28, 11, 10, tzinfo=UTC),
    title="Разработка баз данных",
    kind="ПР",
    room="И-212-б (В-78)",
)
LESSON_LINE = "• 12:40–14:10 ПР Разработка баз данных · И-212-б (В-78)"


def test_lessons_follow_the_reminders_in_my_day() -> None:
    data = day_data(has_schedule=True, lessons=[LESSON], week_label="5 неделя")
    lines = texts.today_text(data, "Alex", RU).splitlines()
    after = lines.index("• 12:30 — встреча")
    assert lines[after + 1 : after + 3] == ["🎓 Пары · 5 неделя:", LESSON_LINE]
    lines = texts.morning_text(data, "Alex", RU).splitlines()
    after = lines.index("• 12:30 — встреча")
    assert lines[after + 1 : after + 3] == ["🎓 Пары · 5 неделя:", LESSON_LINE]


def test_a_connected_day_without_lessons_says_so() -> None:
    text = texts.today_text(day_data(has_schedule=True), "Alex", RU)
    assert "🎓 Пар сегодня нет" in text
    english = texts.morning_text(day_data(has_schedule=True, lessons=[LESSON]), "Alex", EN)
    assert "🎓 Classes:\n" + LESSON_LINE in english


def test_no_timetable_no_lesson_lines() -> None:
    assert "🎓" not in texts.today_text(day_data(), "Alex", RU)


def test_lesson_names_without_a_type_or_a_room() -> None:
    plain = Lesson(uid="u", starts_at=LESSON.starts_at, ends_at=LESSON.ends_at, title="Physics")
    assert texts.lesson_name(plain) == "Physics"
    assert texts.lesson_name(LESSON) == "ПР Разработка баз данных · И-212-б (В-78)"
    assert texts.lesson_alert_text(plain, 15, EN) == "🎓 In 15 min: Physics"


def test_real_lessons_keep_their_room() -> None:
    # MIREA subjects run long and the room comes on top: the fixture's Kotlin lecture is 81
    # characters, the same subject as a lab in the fixture's lab room 85. Neither is clipped.
    for kind, room in (("ЛК", "А-18 (В-78)"), ("ЛАБ", "И-212-б (В-78)")):
        lesson = Lesson(
            uid="u",
            starts_at=LESSON.starts_at,
            ends_at=LESSON.ends_at,
            title="Проектирование и разработка мобильных приложений на языке Котлин",
            kind=kind,
            room=room,
        )
        assert texts.lesson_line(lesson, MSK, RU) == f"• 12:40–14:10 {texts.lesson_name(lesson)}"


def test_lessons_and_reminders_stay_within_the_telegram_message_limit() -> None:
    long = Lesson(
        uid="u",
        starts_at=LESSON.starts_at,
        ends_at=LESSON.ends_at,
        title="Т" * 200,
        kind="ЛАБ",
        room="А" * 100,
    )
    reminders = [
        Reminder(text="x" * 200, due_at=datetime(2026, 9, 28, 9, 30, tzinfo=UTC)) for _ in range(20)
    ]
    data = day_data(
        reminders=reminders, has_schedule=True, lessons=[long] * 12, week_label="12 неделя"
    )
    for render in (texts.today_text, texts.morning_text):
        assert len(render(data, "Alex", RU)) <= 4096
    line = texts.lesson_line(long, MSK, RU)
    assert line.endswith("…") and len(line) <= len("• 12:40–14:10 ") + texts.LESSON_NAME_LIMIT


def test_a_cut_day_or_week_keeps_the_stale_warning() -> None:
    long = Lesson(
        uid="u",
        starts_at=LESSON.starts_at,
        ends_at=LESSON.ends_at,
        title="Т" * 200,
        kind="ЛАБ",
        room="А" * 100,
    )
    day, stale = date(2026, 9, 28), date(2026, 9, 24)
    for text in (
        texts.schedule_day_text(day, day, [long] * 60, "5 неделя", "Europe/Moscow", RU, stale),
        texts.schedule_week_text(day, [long] * 60, "5 неделя", "Europe/Moscow", RU, stale),
    ):
        assert len(text) <= texts.TEXT_LIMIT
        assert text.endswith("\n…\n\n⚠️ Данные от 24 сентября — источник пока недоступен.")


EMOJI_LESSON = Lesson(
    uid="u",
    starts_at=LESSON.starts_at,
    ends_at=LESSON.ends_at,
    title="🎉" * 200,
    kind="ЛАБ",
    room="🎉" * 100,
)
TIPS = [
    Tip("tip-precip-later", {"kind": "rain", "hour": "18:00"}),
    Tip("tip-colder-evening"),
    Tip("tip-wind"),
    Tip("tip-heat"),
]


def fullest_day() -> TodayData:
    """Every field at its maximum, the reminders and the pinned notes made of emoji (two UTF-16
    units each). At 17:00 with classes from 18:00 and rain likely all week: both parts of the way
    to the classes, and «Мой день» tells of tomorrow."""
    long = Lesson(
        uid="u",
        starts_at=at("18:00").astimezone(UTC),
        ends_at=at("21:40").astimezone(UTC),
        title="Т" * 200,
        kind="ДОПДОПЛК",  # 8 characters, the most a kind keeps
        room="А" * 100,
    )
    due = datetime(2026, 9, 28, 9, 30, tzinfo=UTC)
    rainy = forecast_payload()
    rainy["hourly"]["precipitation_probability"] = [100] * 7 * 24
    rainy["daily"]["precipitation_probability_max"] = [100] * 7
    rainy["daily"]["weather_code"] = [61] * 7  # 🌧, two units
    forecast = parse_forecast(rainy, "Г" * 100)
    checklist = note_view("🎉" * 500, [True] * 20)
    return day_data(
        local_now=at("17:00"),
        part_of_day="evening",
        weather=replace(forecast.now, tips=TIPS),
        forecast=forecast,
        reminders=[Reminder(text="🎉" * 200, due_at=due) for _ in range(20)],
        # Each line of habits at its longest: «10 из 10» in «Мой день», 10 to mark in the digest.
        habits=[habit_today(None)] * 10,
        habits_total=10,
        habits_done=10,
        best_streak=Streak("П" * 50, 3650, "days"),
        notes_count=50,
        pinned=[checklist] * 3,
        has_schedule=True,
        lessons=[long] * 12,
        week_label="Н" * 40,
    )


FULLEST_LESSON = "• 18:00–21:40 "
FULLEST_WAY = {
    "ru": "🎓 На пары (18:00): +12°C, 💧 100 % · после пар (21:40): +9°C, 💧 100 %",
    "en": "🎓 To classes (18:00): +12°C, 💧 100% · after (21:40): +9°C, 💧 100%",
}
FULLEST_TOMORROW = {"ru": "Завтра: 🌧 +6…+13°C, 💧 100 %", "en": "Tomorrow: 🌧 +6…+13°C, 💧 100%"}


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
@pytest.mark.parametrize("render", [texts.today_text, texts.morning_text], ids=["day", "morning"])
def test_my_day_and_the_digest_fit_telegram_however_full_the_day(t, render) -> None:
    text = render(fullest_day(), "Ж" * 64, t)
    assert utf16(text) <= BUDGET
    lines = text.splitlines()
    assert "Ж" * 64 in lines[0] and "Г" * 100 in lines[3]  # the header and the weather stay
    # So do the weather's other lines and, in «Мой день», the pinned notes.
    my_day = render is texts.today_text
    assert lines[4 : lines.index("", 3)] == [
        *texts.tip_lines(TIPS[:1] if my_day else TIPS, t),
        FULLEST_WAY[t.lang],
        *([FULLEST_TOMORROW[t.lang]] if my_day else []),
        t("weather-credit"),
    ]
    if my_day:
        notes = lines.index(t("today-notes", count=50))
        pinned = t("note-progress", text="🎉" * 39 + "…", done=20, total=20)
        assert lines[notes + 1 : notes + 4] == [t("today-pinned", text=pinned)] * 3
    reminders = [index for index, line in enumerate(lines) if line.endswith("🎉")]
    assert 0 < len(reminders) < texts.DAY_REMINDERS_SHOWN  # cut from the end, first
    assert lines[reminders[-1] + 1] == t("list-more", count=20 - len(reminders))
    lessons = [line for line in lines if line.startswith(FULLEST_LESSON)]
    assert len(lessons) == texts.DAY_LESSONS_SHOWN and t("list-more", count=2) in lines


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
@pytest.mark.parametrize("render", [texts.today_text, texts.morning_text], ids=["day", "morning"])
def test_the_lessons_are_cut_once_no_reminder_is_left(t, render, monkeypatch) -> None:
    monkeypatch.setattr(texts, "TEXT_LIMIT", 1500)
    text = render(fullest_day(), "Alex", t)
    assert utf16(text) <= 1500
    lines = text.splitlines()
    assert not any(line.endswith("🎉") for line in lines) and t("list-more", count=20) in lines
    lessons = [index for index, line in enumerate(lines) if line.startswith(FULLEST_LESSON)]
    assert 0 < len(lessons) < texts.DAY_LESSONS_SHOWN
    assert lines[lessons[-1] + 1] == t("list-more", count=12 - len(lessons))


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
def test_a_day_or_a_week_of_emoji_titles_fits_telegram(t) -> None:
    day, stale = date(2026, 9, 28), date(2026, 9, 24)
    warning = t("schedule-stale", date=format_day(stale, t.lang))
    for text in (
        texts.schedule_day_text(
            day, day, [EMOJI_LESSON] * 60, "🎉" * 40, "Europe/Moscow", t, stale
        ),
        texts.schedule_week_text(day, [EMOJI_LESSON] * 60, "🎉" * 40, "Europe/Moscow", t, stale),
    ):
        assert utf16(text) <= BUDGET and text.endswith(f"\n…\n\n{warning}")


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
def test_every_list_fits_telegram_at_its_maxima(t) -> None:
    due = datetime(2026, 9, 28, 9, 30, tzinfo=UTC)
    # The longest page of notes: five pinned checklists of 500 emoji with 20 items each.
    checklist = [Item(n, "🎉" * 100, True) for n in range(1, 21)]
    notes = [
        NoteView(n, "🎉" * 500, due if n <= 5 else None, due, due, checklist) for n in range(1, 51)
    ]
    pending = [
        Reminder(id=n, user_id=1, text="🎉" * 200, due_at=due, repeat=Repeat.NONE)
        for n in range(1, 21)
    ]
    stats = [
        HabitStats(
            habit=Habit(id=n, name="🎉" * 50, weekly_goal=7, emoji="🎯"),
            today=date(2026, 9, 28),
            done_today=None,
            streak=3650,
            done_days=3650,
            total_days=3650,
            last_days=(True,) * 9,
            record=3650,
            percent=100,
            week_done=7,
            week_goal=7,
            week="1111111",
        )
        for n in range(1, 11)
    ]
    page, _ = notes_view(notes, 0, t)
    # A note's line keeps 100 characters, so the page is never cut: the title, five notes, the
    # page line.
    lines = page.splitlines()
    assert utf16(page) <= BUDGET and len(lines) == 9
    assert all("📌" in line for line in lines[2:7]) and lines[-1] == t("page", current=1, total=10)
    user = User(id=1, timezone="Europe/Moscow")
    assert utf16(reminders_view(pending, 0, user, t)[0]) <= BUDGET
    assert utf16(habits_view(stats, t)[0]) <= BUDGET


def test_a_cut_list_keeps_its_tail_measured_like_telegram_too() -> None:
    tail = ["", "🎉" * 1000]  # 1000 characters, 2000 units
    text = texts.fit(["x" * 100] * 30, tail)
    assert utf16(text) <= BUDGET and text.endswith("\n…\n\n" + "🎉" * 1000)


def test_a_lesson_without_an_end_shows_its_start_only() -> None:
    # An event with neither DTEND nor DURATION ends when it starts.
    point = Lesson(
        uid="u", starts_at=LESSON.starts_at, ends_at=LESSON.starts_at, title="Консультация"
    )
    assert texts.lesson_line(point, MSK, RU) == "• 12:40 Консультация"
    assert texts.lesson_line(point, MSK, EN) == "• 12:40 Консультация"
    assert texts.lesson_line(LESSON, MSK, RU) == LESSON_LINE


def test_schedule_texts_promise_no_cause_or_time_they_cannot_know() -> None:
    # A calendar is refused for its size, its time, its memory, its series or its labels alike;
    # a directory cut short by an outage is retried a day later, not in half an hour.
    assert texts.schedule_error_text("too_large", RU) == (
        "⚠️ Календарь слишком большой или сложный — разобрать его не получится."
    )
    assert texts.schedule_error_text("too_large", EN) == (
        "⚠️ The calendar is too big or too complex to read."
    )
    assert RU("schedule-directory-empty") == (
        "Справочник групп МИРЭА ещё не готов — попробуй позже или подключи расписание по ссылке."
    )
    assert EN("schedule-directory-empty") == (
        "The MIREA group directory isn't ready yet — try again later"
        " or connect a timetable by link."
    )


def money_month(**changes: object) -> Month:
    values: dict[str, object] = {
        "first": date(2026, 9, 1),
        "today": date(2026, 9, 28),
        "spent": 1240000,
        "income": 0,
        "budget": 3000000,
        "left": 1760000,
        "per_day": 586666,
        "expenses": [],
        "incomes": [],
        "days": [0] * 27 + [65000, None, None],
        "count": 14,
    }
    values.update(changes)
    return Month(**values)  # type: ignore[arg-type]


def money_line(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith("💰")]


def test_my_day_shows_todays_spending_and_the_month() -> None:
    data = day_data(money=money_month(), spent_today=65000)
    assert money_line(texts.today_text(data, "Alex", RU)) == [
        f"💰 Сегодня: 650{NBSP}₽ · сентябрь: 12{NBSP}400{NBSP}₽ из 30{NBSP}000{NBSP}₽"
    ]
    plain = day_data(money=money_month(budget=None, left=None, per_day=None), spent_today=0)
    assert money_line(texts.today_text(plain, "Alex", EN)) == [
        f"💰 Today: 0{NBSP}₽ · September: 12,400{NBSP}₽"
    ]
    nothing = day_data(money=money_month(count=0, spent=0))
    assert money_line(texts.today_text(nothing, "Alex", RU)) == []


def test_the_morning_shows_yesterday_and_the_rest_for_each_day() -> None:
    data = day_data(money=money_month(), spent_yesterday=125000)
    assert money_line(texts.morning_text(data, "Alex", RU)) == [
        f"💰 Вчера: 1{NBSP}250{NBSP}₽ · осталось 17{NBSP}600{NBSP}₽ — "
        f"по 5{NBSP}866,66{NBSP}₽ в день"
    ]
    over = day_data(money=money_month(left=-300000, per_day=None), spent_yesterday=0)
    assert money_line(texts.morning_text(over, "Alex", RU)) == [
        f"💰 Вчера: 0{NBSP}₽ · перерасход 3{NBSP}000{NBSP}₽"
    ]
    plain = money_month(budget=None, left=None, per_day=None)
    assert money_line(texts.morning_text(day_data(money=plain, spent_yesterday=500), "A", EN)) == [
        f"💰 Yesterday: 5{NBSP}₽"
    ]
    assert money_line(texts.morning_text(day_data(money=plain, spent_yesterday=0), "A", RU)) == []


def test_my_day_shows_the_users_own_currency_beside_the_dollar_and_the_euro() -> None:
    rates = Rates(RATES.day, RATES.usd, RATES.eur, currencies={"KZT": Rate(0.1631, 0.0012)})
    lines = texts.today_text(day_data(rates=rates, currency="KZT"), "Alex", RU).split("\n")
    assert "💵 84,20 ₽ · 💶 96,67 ₽ · 💱 KZT 0,1631 ₽" in lines
    morning = texts.morning_text(day_data(rates=rates, currency="RUB"), "Alex", RU).split("\n")
    assert "💵 84,20 ₽ · 💶 96,67 ₽" in morning
