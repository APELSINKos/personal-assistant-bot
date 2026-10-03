from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from assistant.bot import texts
from assistant.bot.routers.habits import habits_view
from assistant.bot.routers.notes import notes_view
from assistant.bot.routers.reminders import reminders_view
from assistant.core.clients.cbr import Rate, Rates
from assistant.core.i18n import format_day, translator
from assistant.core.models import Habit, Lesson, Note, Reminder, Repeat, User
from assistant.core.services.digest import TodayData
from assistant.core.services.habits import HabitStats, Streak
from assistant.core.services.money_month import Month
from assistant.core.services.weather import Tip, WeatherNow

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
    """Every field at its maximum, the reminders made of emoji (two UTF-16 units each)."""
    long = Lesson(
        uid="u",
        starts_at=LESSON.starts_at,
        ends_at=LESSON.ends_at,
        title="Т" * 200,
        kind="ДОПДОПЛК",  # 8 characters, the most a kind keeps
        room="А" * 100,
    )
    due = datetime(2026, 9, 28, 9, 30, tzinfo=UTC)
    return day_data(
        weather=replace(WEATHER, city="Г" * 100, tips=TIPS),
        reminders=[Reminder(text="🎉" * 200, due_at=due) for _ in range(20)],
        habits_total=10,
        habits_done=10,
        best_streak=Streak("П" * 50, 3650, "days"),
        notes_count=50,
        has_schedule=True,
        lessons=[long] * 12,
        week_label="Н" * 40,
    )


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
@pytest.mark.parametrize("render", [texts.today_text, texts.morning_text], ids=["day", "morning"])
def test_my_day_and_the_digest_fit_telegram_however_full_the_day(t, render) -> None:
    text = render(fullest_day(), "Ж" * 64, t)
    assert utf16(text) <= BUDGET
    lines = text.splitlines()
    assert "Ж" * 64 in lines[0] and "Г" * 100 in lines[3]  # the header and the weather stay
    reminders = [index for index, line in enumerate(lines) if line.endswith("🎉")]
    assert 0 < len(reminders) < texts.DAY_REMINDERS_SHOWN  # cut from the end, first
    assert lines[reminders[-1] + 1] == t("list-more", count=20 - len(reminders))
    lessons = [line for line in lines if line.startswith("• 12:40–14:10")]
    assert len(lessons) == texts.DAY_LESSONS_SHOWN and t("list-more", count=2) in lines


@pytest.mark.parametrize("t", [RU, EN], ids=["ru", "en"])
@pytest.mark.parametrize("render", [texts.today_text, texts.morning_text], ids=["day", "morning"])
def test_the_lessons_are_cut_once_no_reminder_is_left(t, render, monkeypatch) -> None:
    monkeypatch.setattr(texts, "TEXT_LIMIT", 1500)
    text = render(fullest_day(), "Alex", t)
    assert utf16(text) <= 1500
    lines = text.splitlines()
    assert not any(line.endswith("🎉") for line in lines) and t("list-more", count=20) in lines
    lessons = [index for index, line in enumerate(lines) if line.startswith("• 12:40–14:10")]
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
    notes = [Note(id=n, user_id=1, text="🎉" * 500) for n in range(1, 51)]
    pending = [
        Reminder(id=n, user_id=1, text="🎉" * 200, due_at=due, repeat=Repeat.NONE)
        for n in range(1, 21)
    ]
    stats = [
        HabitStats(
            habit=Habit(id=n, name="🎉" * 50, weekly_goal=7, emoji="🎯"),
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
    assert utf16(page) <= BUDGET and page.endswith(f"\n…\n\n{t('page', current=1, total=10)}")
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
