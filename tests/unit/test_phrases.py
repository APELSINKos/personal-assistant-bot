from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from assistant.core.models import Repeat
from assistant.core.services.phrases import Parsed, dump, load, merge, parse

NOW = datetime(2026, 9, 28, 15, 0)  # Monday, 15:00 local


def summary(parsed: Parsed | None) -> str | None:
    """A compact, readable form of what a phrase was understood as."""
    if parsed is None:
        return None
    if parsed.repeat is Repeat.NONE:
        when = parsed.when(NOW)
        return f"{parsed.text} | {when:%Y-%m-%d %H:%M}" if when else f"{parsed.text} | needs time"
    rule = parsed.rule(NOW)
    if rule is None:
        return f"{parsed.text} | {parsed.repeat.value} needs time"
    if rule.repeat is Repeat.DAILY:
        return f"{parsed.text} | daily {rule.time_local}"
    if rule.repeat is Repeat.MONTHLY:
        return f"{parsed.text} | monthly {rule.month_day} {rule.time_local}"
    if rule.interval_weeks == 2:
        return f"{parsed.text} | biweekly {rule.weekdays} {rule.time_local} from {rule.anchor_date}"
    return f"{parsed.text} | weekly {rule.weekdays} {rule.time_local}"


CASES = [
    # --- Russian: one-off with a clock time
    ("завтра в 9 купить молоко", "купить молоко | 2026-09-29 09:00"),
    ("Напомни мне завтра в 9 купить молоко", "купить молоко | 2026-09-29 09:00"),
    ("напомнить в 18:30 позвонить маме", "позвонить маме | 2026-09-28 18:30"),
    ("в 9 зарядка", "зарядка | 2026-09-29 09:00"),
    ("в 21.00 таблетки", "таблетки | 2026-09-28 21:00"),
    ("в 7 вечера тренировка", "тренировка | 2026-09-28 19:00"),
    ("в 9 утра пробежка", "пробежка | 2026-09-29 09:00"),
    ("в 3 дня созвон", "созвон | 2026-09-29 15:00"),
    ("в 11 ночи отбой", "отбой | 2026-09-28 23:00"),
    ("в 2 ночи проверить сервер", "проверить сервер | 2026-09-29 02:00"),
    ("в полдень обед", "обед | 2026-09-29 12:00"),
    ("в полночь поздравить Сашу", "поздравить Сашу | 2026-09-29 00:00"),
    ("к 18 сдать отчёт", "сдать отчёт | 2026-09-28 18:00"),
    ("в 9 часов планёрка", "планёрка | 2026-09-29 09:00"),
    ("18:30 созвон", "созвон | 2026-09-28 18:30"),
    ("созвон 18:30", "созвон | 2026-09-28 18:30"),
    ("завтра в 9:05 созвон", "созвон | 2026-09-29 09:05"),
    ("в 9 утра завтра врач", "врач | 2026-09-29 09:00"),
    ("Созвон с командой завтра в 19:30", "Созвон с командой | 2026-09-29 19:30"),
    ("в 10.12 встреча", "встреча | 2026-09-29 10:12"),
    ("в 0:30 выключить свет", "выключить свет | 2026-09-29 00:30"),
    ("в  10.12 встреча", "встреча | 2026-09-29 10:12"),
    ("сегодня вечером в 8 кино", "кино | 2026-09-28 20:00"),
    ("завтра утром в 7 пробежка", "пробежка | 2026-09-29 07:00"),
    ("в 8 вечером кино", "кино | 2026-09-28 20:00"),
    ("в 7 метро встреча", "метро встреча | 2026-09-29 07:00"),
    ("в 10 рубить дрова", "рубить дрова | 2026-09-29 10:00"),
    ("в 9 годовщина свадьбы", "годовщина свадьбы | 2026-09-29 09:00"),
    ("напомни мне, пожалуйста, завтра в 9 купить молоко", "купить молоко | 2026-09-29 09:00"),
    # --- Russian: relative
    ("через 20 минут чай", "чай | 2026-09-28 15:20"),
    ("через полчаса выключить духовку", "выключить духовку | 2026-09-28 15:30"),
    ("через час позвонить", "позвонить | 2026-09-28 16:00"),
    ("через 2 часа забрать посылку", "забрать посылку | 2026-09-28 17:00"),
    ("через полтора часа выйти", "выйти | 2026-09-28 16:30"),
    ("через минуту тест", "тест | 2026-09-28 15:01"),
    ("через пять минут проверить", "проверить | 2026-09-28 15:05"),
    ("через 20 минут, чай", "чай | 2026-09-28 15:20"),
    ("через 3 дня в 10 врач", "врач | 2026-10-01 10:00"),
    ("через неделю в 12 оплатить", "оплатить | 2026-10-05 12:00"),
    ("через 2 недели в 9 анализы", "анализы | 2026-10-12 09:00"),
    ("через 3 дня позвонить бабушке", "позвонить бабушке | needs time"),
    ("через 1 час 30 минут чай", "чай | 2026-09-28 16:30"),
    ("через 2 часа 15 минут забрать", "забрать | 2026-09-28 17:15"),
    ("через час 20 минут выйти", "выйти | 2026-09-28 16:20"),
    # --- Russian: days, weekdays, dates
    ("послезавтра в 10 стоматолог", "стоматолог | 2026-09-30 10:00"),
    ("сегодня в 20 кино", "кино | 2026-09-28 20:00"),
    ("сегодня в 10 кино", "кино | 2026-09-28 10:00"),  # in the past: the service refuses it
    ("в пятницу в 18 созвон", "созвон | 2026-10-02 18:00"),
    ("во вторник в 10:40 пара", "пара | 2026-09-29 10:40"),
    ("в понедельник в 9 планёрка", "планёрка | 2026-10-05 09:00"),
    ("в понедельник в 16 планёрка", "планёрка | 2026-09-28 16:00"),
    ("в воскресенье в 12 обед у бабушки", "обед у бабушки | 2026-10-04 12:00"),
    ("в среду купить подарок", "купить подарок | needs time"),
    ("25.09 в 18:30 встреча", "встреча | 2027-09-25 18:30"),
    ("05.10 в 12 оплатить", "оплатить | 2026-10-05 12:00"),
    ("10.12 в 18 встреча", "встреча | 2026-12-10 18:00"),
    ("25.09.2027 в 18:30 юбилей", "юбилей | 2027-09-25 18:30"),
    ("25 сентября в 10 день рождения", "день рождения | 2027-09-25 10:00"),
    ("5 октября в 12:00 оплатить интернет", "оплатить интернет | 2026-10-05 12:00"),
    ("1 января 2027 в 0:00 салют", "салют | 2027-01-01 00:00"),
    ("1 января 2027 года в 10 салют", "салют | 2027-01-01 10:00"),
    ("купить ёлку 30 декабря в 18", "купить ёлку | 2026-12-30 18:00"),
    ("завтра позвонить маме", "позвонить маме | needs time"),
    ("напомни завтра, что нужно позвонить", "нужно позвонить | needs time"),
    ("завтра", " | needs time"),
    ("в 9", " | 2026-09-29 09:00"),
    ("25.09.27 в 18 встреча", "встреча | 2027-09-25 18:00"),
    ("в 10.12.2026 в 18 встреча", "встреча | 2026-12-10 18:00"),
    ("на 05.10.2026 в 9 экзамен", "экзамен | 2026-10-05 09:00"),
    ("28.09 в 10 отчёт", "отчёт | 2026-09-28 10:00"),
    ("в следующую пятницу в 10 врач", "врач | 2026-10-09 10:00"),
    ("в следующий понедельник в 9 планёрка", "планёрка | 2026-10-05 09:00"),
    ("в эту пятницу в 10 врач", "врач | 2026-10-02 10:00"),
    ("на завтра в 9 купить молоко", "купить молоко | 2026-09-29 09:00"),
    ("на пятницу в 10 врач", "врач | 2026-10-02 10:00"),
    ("31.02 в 10 встреча", None),
    ("31 февраля в 10 встреча", None),
    ("29.02.2027 в 10 поздравить", None),
    # --- Russian: repeats
    ("каждый день в 21 таблетки", "таблетки | daily 21:00"),
    ("ежедневно в 8:00 витамины", "витамины | daily 08:00"),
    ("Каждый День В 21 Таблетки", "Таблетки | daily 21:00"),
    ("напомни каждый день в 22 спать", "спать | daily 22:00"),
    ("каждый день в 21:00 таблетки!", "таблетки! | daily 21:00"),
    ("по будням в 7:30 зарядка", "зарядка | weekly 31 07:30"),
    ("в будни в 8 подъём", "подъём | weekly 31 08:00"),
    ("каждый будний день в 9 почта", "почта | weekly 31 09:00"),
    ("по выходным в 11 уборка", "уборка | weekly 96 11:00"),
    ("в выходные в 10 блины", "блины | weekly 96 10:00"),
    ("каждый понедельник в 10 планёрка", "планёрка | weekly 1 10:00"),
    ("каждую среду в 9 практика", "практика | weekly 4 09:00"),
    ("каждое воскресенье в 20 звонок родителям", "звонок родителям | weekly 64 20:00"),
    ("по вторникам и четвергам в 10:40 пара", "пара | weekly 10 10:40"),
    ("по понедельникам, средам и пятницам в 7 бег", "бег | weekly 21 07:00"),
    ("каждый вторник и четверг в 12 обед с Машей", "обед с Машей | weekly 10 12:00"),
    ("раз в две недели по средам в 9 практика", "практика | biweekly 4 09:00 from 2026-09-30"),
    ("раз в 2 недели в среду в 9 практика", "практика | biweekly 4 09:00 from 2026-09-30"),
    ("каждую вторую среду в 9 практика", "практика | biweekly 4 09:00 from 2026-09-30"),
    (
        "раз в две недели по понедельникам в 16 семинар",
        "семинар | biweekly 1 16:00 from 2026-09-28",
    ),
    ("раз в две недели по понедельникам в 9 семинар", "семинар | biweekly 1 09:00 from 2026-10-05"),
    ("раз в две недели в 18 созвон", "созвон | biweekly 1 18:00 from 2026-09-28"),
    ("каждый месяц 5 числа в 12 оплатить интернет", "оплатить интернет | monthly 5 12:00"),
    ("каждый месяц 5-го в 12 оплатить", "оплатить | monthly 5 12:00"),
    ("каждое 1 число в 10 отчёт", "отчёт | monthly 1 10:00"),
    ("15 числа каждого месяца в 9 зарплата", "зарплата | monthly 15 09:00"),
    ("ежемесячно 31 числа в 12 аренда", "аренда | monthly 31 12:00"),
    ("каждый день таблетки", "таблетки | daily needs time"),
    ("по будням зарядка", "зарядка | weekly needs time"),
    ("каждый день через 20 минут пить воду", "через 20 минут пить воду | daily needs time"),
    ("каждый месяц 45 числа в 10 оплатить", None),
    ("каждый месяц 0 числа в 10 оплатить", None),
    # --- English
    ("tomorrow at 9 buy milk", "buy milk | 2026-09-29 09:00"),
    ("remind me to call mom at 6pm", "call mom | 2026-09-28 18:00"),
    ("Remind me to call Mom at 6 pm", "call Mom | 2026-09-28 18:00"),
    ("at 9:30 standup", "standup | 2026-09-29 09:30"),
    ("9pm pills", "pills | 2026-09-28 21:00"),
    ("7 am run", "run | 2026-09-29 07:00"),
    ("at 12am backup", "backup | 2026-09-29 00:00"),
    ("at noon lunch", "lunch | 2026-09-29 12:00"),
    ("at midnight backup", "backup | 2026-09-29 00:00"),
    ("in 20 minutes tea", "tea | 2026-09-28 15:20"),
    ("in an hour call back", "call back | 2026-09-28 16:00"),
    ("in 2 hours pick up the parcel", "pick up the parcel | 2026-09-28 17:00"),
    ("in half an hour oven", "oven | 2026-09-28 15:30"),
    ("in five minutes check", "check | 2026-09-28 15:05"),
    ("in 3 days at 10 doctor", "doctor | 2026-10-01 10:00"),
    ("in a week at 12 pay rent", "pay rent | 2026-10-05 12:00"),
    ("the day after tomorrow at 10 dentist", "dentist | 2026-09-30 10:00"),
    ("today at 8pm movie", "movie | 2026-09-28 20:00"),
    ("on friday at 6pm call", "call | 2026-10-02 18:00"),
    ("on monday at 9 meeting", "meeting | 2026-10-05 09:00"),
    ("on 25 september at 10 birthday", "birthday | 2027-09-25 10:00"),
    ("sep 25 at 10 birthday", "birthday | 2027-09-25 10:00"),
    ("october 5 at noon pay", "pay | 2026-10-05 12:00"),
    ("5 oct 2027 at 9 exam", "exam | 2027-10-05 09:00"),
    ("tomorrow call mom", "call mom | needs time"),
    ("every day at 9pm pills", "pills | daily 21:00"),
    ("daily at 8 vitamins", "vitamins | daily 08:00"),
    ("on weekdays at 7:30 workout", "workout | weekly 31 07:30"),
    ("every weekday at 9 mail", "mail | weekly 31 09:00"),
    ("every weekend at 11 cleaning", "cleaning | weekly 96 11:00"),
    ("every monday at 10 planning", "planning | weekly 1 10:00"),
    ("every tuesday and thursday at 10:40 class", "class | weekly 10 10:40"),
    ("on mondays at 9 gym", "gym | weekly 1 09:00"),
    ("every other wednesday at 9 practice", "practice | biweekly 4 09:00 from 2026-09-30"),
    ("monthly on the 5th at noon pay internet", "pay internet | monthly 5 12:00"),
    ("every month on the 1st at 10 report", "report | monthly 1 10:00"),
    ("on the 15th of every month at 9 salary", "salary | monthly 15 09:00"),
    ("remind me to stretch every day", "stretch | daily needs time"),
    ("in 1 hour 30 minutes tea", "tea | 2026-09-28 16:30"),
    ("in 2 hours and 15 minutes call", "call | 2026-09-28 17:15"),
    ("at 9 p.m. pills", "pills | 2026-09-28 21:00"),
    ("at 9.30pm dinner", "dinner | 2026-09-28 21:30"),
    ("at 7 a.m. run", "run | 2026-09-29 07:00"),
    ("friday at 6pm call mom", "call mom | 2026-10-02 18:00"),
    ("next friday at 10 doctor", "doctor | 2026-10-09 10:00"),
    ("please remind me to call mom at 6pm", "call mom | 2026-09-28 18:00"),
    # --- not reminders: no time anchor at all
    ("купить 2 батона", None),
    ("у меня 3 пары", None),
    ("сдал на 5", None),
    ("привет", None),
    ("как дела?", None),
    ("2+2", None),
    ("в магазине", None),
    ("25 лет", None),
    ("в 25:00 что-то", None),
    ("hello there", None),
    ("call mom", None),
    ("I have 3 classes", None),
    ("", None),
    # --- not reminders: numbers that are not times
    ("в 2 раза дешевле", None),
    ("в 3 классе", None),
    ("живу в 10 минутах от метро", None),
    ("в 10 км от дома", None),
    ("в 9-м классе", None),
    ("в 5% случаев", None),
    ("купил 2.5 кг яблок", None),
    ("рейтинг 4.8", None),
    ("rated at 5 stars", None),
]


@pytest.mark.parametrize(("message", "expected"), CASES, ids=[c[0] or "empty" for c in CASES])
def test_parse(message: str, expected: str | None) -> None:
    assert summary(parse(message, NOW)) == expected


def test_there_are_plenty_of_cases() -> None:
    assert len(CASES) >= 120


def test_with_time_completes_a_phrase() -> None:
    parsed = parse("завтра позвонить маме", NOW)
    assert parsed is not None and parsed.needs_time
    done = parsed.with_time("18:00")
    assert not done.needs_time and done.when(NOW) == datetime(2026, 9, 29, 18, 0)


@pytest.mark.parametrize(
    ("first", "answer", "expected"),
    [
        ("завтра позвонить маме", "в 18", "позвонить маме | 2026-09-29 18:00"),
        ("завтра позвонить маме", "18:30", "позвонить маме | 2026-09-29 18:30"),
        ("в пятницу купить подарок", "в 10", "купить подарок | 2026-10-02 10:00"),
        ("каждый день таблетки", "в 21", "таблетки | daily 21:00"),
        ("завтра в 9 купить молоко", "послезавтра в 10", "купить молоко | 2026-09-30 10:00"),
        ("завтра в 9 купить молоко", "через 20 минут", "купить молоко | 2026-09-28 15:20"),
        ("завтра в 9 купить молоко", "по будням в 8", "купить молоко | weekly 31 08:00"),
        ("завтра", "в 18 созвон", "созвон | 2026-09-29 18:00"),
        ("каждый день в 21 таблетки", "в 9", "таблетки | daily 09:00"),
        ("каждый день в 21 таблетки", "через 20 минут", "таблетки | 2026-09-28 15:20"),
        ("каждый день в 21 таблетки", "завтра в 10", "таблетки | 2026-09-29 10:00"),
        ("каждый понедельник в 10 планёрка", "в среду", "планёрка | weekly 4 10:00"),
        (
            "раз в две недели по средам в 9 практика",
            "в пятницу",
            "практика | biweekly 16 09:00 from 2026-10-02",
        ),
        ("каждый месяц 5 числа в 12 оплатить", "в пятницу в 10", "оплатить | 2026-10-02 10:00"),
    ],
)
def test_merge_an_answer(first: str, answer: str, expected: str) -> None:
    base, extra = parse(first, NOW), parse(answer, NOW)
    assert base is not None and extra is not None
    assert summary(merge(base, extra)) == expected


@pytest.mark.parametrize(
    "message",
    [
        "через 20 минут чай",
        "25.09 в 18:30 встреча",
        "раз в две недели по средам в 9 практика",
        "каждый месяц 5 числа в 12 оплатить",
        "в пятницу купить подарок",
    ],
)
def test_dump_and_load_round_trip(message: str) -> None:
    parsed = parse(message, NOW)
    assert parsed is not None
    assert load(json.loads(json.dumps(dump(parsed)))) == parsed


@pytest.mark.parametrize(
    ("now", "message", "expected"),
    [
        (datetime(2027, 3, 1, 12, 0), "29.02 в 10 поздравить", datetime(2028, 2, 29, 10, 0)),
        (datetime(2028, 2, 1, 12, 0), "29.02 в 10 поздравить", datetime(2028, 2, 29, 10, 0)),
        (datetime(2028, 3, 1, 12, 0), "29.02 в 10 поздравить", datetime(2032, 2, 29, 10, 0)),
        (datetime(2028, 3, 1, 12, 0), "29 февраля в 10 поздравить", datetime(2032, 2, 29, 10, 0)),
        (datetime(2027, 3, 1, 12, 0), "feb 29 at 10 congratulate", datetime(2028, 2, 29, 10, 0)),
    ],
)
def test_leap_day_goes_to_the_next_leap_year(
    now: datetime, message: str, expected: datetime
) -> None:
    parsed = parse(message, now)
    assert parsed is not None and parsed.text in ("поздравить", "congratulate")
    assert parsed.when(now) == expected
    assert load(json.loads(json.dumps(dump(parsed)))) == parsed


def test_a_repeat_with_a_delta_still_needs_a_time() -> None:
    odd = Parsed(text="x", repeat=Repeat.DAILY, delta=timedelta(minutes=20))
    assert odd.needs_time


def test_every_other_week_without_days_has_no_rule() -> None:
    odd = Parsed(text="x", time="09:00", repeat=Repeat.WEEKLY, weekdays=0, interval_weeks=2)
    assert odd.rule(NOW) is None
