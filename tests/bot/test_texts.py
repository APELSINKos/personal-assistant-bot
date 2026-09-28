from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from assistant.bot import texts
from assistant.core.clients.cbr import Rate, Rates
from assistant.core.i18n import translator
from assistant.core.models import Reminder
from assistant.core.services.digest import TodayData
from assistant.core.services.weather import Tip, WeatherNow

RU, EN = translator("ru"), translator("en")
MSK = ZoneInfo("Europe/Moscow")
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


def day_data(**changes: object) -> TodayData:
    values: dict[str, object] = {
        "local_now": datetime(2026, 9, 28, 8, 0, tzinfo=MSK),
        "part_of_day": "morning",
        "weather": WEATHER,
        "reminders": [Reminder(text="встреча", due_at=datetime(2026, 9, 28, 9, 30, tzinfo=UTC))],
        "habits": [],
        "habits_done": 1,
        "habits_total": 3,
        "notes_count": 4,
        "rates": RATES,
        "best_streak": ("Спорт", 5),
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
        "🚲 Сегодня хороший день для велосипеда"
    )


def test_today_text_full() -> None:
    assert texts.today_text(day_data(), "Alex", RU) == (
        "🌅 Доброе утро, Alex!\n"
        "📅 Сегодня, 28 сентября, понедельник\n"
        "\n"
        "🌤 Москва: +10°C, малооблачно\n"
        "🚲 Сегодня хороший день для велосипеда\n"
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
    text = texts.today_text(day_data(best_streak=("Run", 1)), "Alex", EN)
    assert "📅 Today, Monday, September 28" in text
    assert "📌 1 reminder for today:" in text
    assert "🔥 Best streak: “Run” — 1 day" in text


def test_morning_text() -> None:
    assert texts.morning_text(day_data(), "Alex", RU) == (
        "☀️ Доброе утро, Alex!\n"
        "📅 28 сентября, понедельник\n"
        "\n"
        "🌡 Москва: +6…+13°C\n"
        "🚲 Сегодня хороший день для велосипеда\n"
        "\n"
        "📌 Сегодня:\n"
        "• 12:30 — встреча\n"
        "\n"
        "🎯 Привычек на сегодня: 3 — не забудь отметить\n"
        "🔥 Лучшая серия: «Спорт» — 5 дней\n"
        "💵 84,20 ₽ · 💶 96,67 ₽"
    )


def test_morning_text_minimal() -> None:
    data = day_data(weather=None, reminders=[], habits_total=0, best_streak=None, rates=None)
    assert texts.morning_text(data, "Alex", RU) == (
        "☀️ Доброе утро, Alex!\n"
        "📅 28 сентября, понедельник\n"
        "\n"
        "🌤 Погода временно недоступна\n"
        "\n"
        "📌 На сегодня напоминаний нет"
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
    assert texts.rates_text(RATES, RU) == (
        "💱 Курс ЦБ РФ на 28 сентября\n"
        "\n"
        "💵 USD: 84,20 ₽  ▼ 0,31\n"
        "💶 EUR: 96,67 ₽  • 0,00\n"
        "\n"
        "Конвертер 👇"
    )
