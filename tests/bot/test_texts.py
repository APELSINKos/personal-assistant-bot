from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from assistant.bot import texts
from assistant.core.clients.cbr import Rate, Rates
from assistant.core.i18n import translator
from assistant.core.models import Lesson, Reminder
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
        assert len(text) <= texts.SCHEDULE_TEXT_LIMIT
        assert text.endswith("\n…\n\n⚠️ Данные от 24 сентября — источник пока недоступен.")
