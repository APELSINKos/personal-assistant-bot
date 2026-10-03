from __future__ import annotations

import pytest

from assistant.core.services.money_phrases import (
    OtherCurrency,
    Quick,
    dictionary_guess,
    format_amount,
    note_key,
    parse_quick,
    to_hundredths,
)

NBSP = "\u00a0"


@pytest.mark.parametrize(
    ("number", "thousands", "expected"),
    [
        ("250", False, 25000),
        ("1 200", False, 120000),
        (f"1{NBSP}200", False, 120000),
        ("430,50", False, 43050),
        ("430.5", False, 43050),
        ("1,200", False, 120000),  # three digits after the separator group thousands
        ("1.200", False, 120000),
        ("12,345", False, 1234500),
        ("1 200,500", False, None),  # grouped, then thousands again
        ("2", True, 200000),
        ("1,5", True, 150000),
        ("1,250", True, 125000),
        ("0", False, None),
        ("1000000000", False, 100000000000),
        ("1000000001", False, None),
        ("abc", False, None),
    ],
)
def test_amounts_in_hundredths(number: str, thousands: bool, expected: int | None) -> None:
    assert to_hundredths(number, thousands) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("кофе 250", Quick(25000, "кофе", None)),
        ("Кофе 250", Quick(25000, "Кофе", None)),
        ("такси 430,50", Quick(43050, "такси", None)),
        ("продукты 1 200", Quick(120000, "продукты", None)),
        ("продукты 2к", Quick(200000, "продукты", None)),
        ("аренда 25 тыс", Quick(2500000, "аренда", None)),
        ("кофе 250₽", Quick(25000, "кофе", None)),
        ("кофе 250 ₽", Quick(25000, "кофе", None)),
        ("кофе 250 р", Quick(25000, "кофе", None)),
        ("кофе 250 руб.", Quick(25000, "кофе", None)),
        ("кофе 12.50", Quick(1250, "кофе", None)),
        ("купил хлеб за 85", Quick(8500, "купил хлеб", None)),
        ("iphone 15 75000", Quick(7500000, "iphone 15", None)),
        ("+5000 стипендия", Quick(500000, "стипендия", True)),
        ("+5000 за стипендию", Quick(500000, "стипендию", True)),
        ("-250 кофе", Quick(25000, "кофе", False)),
        ("кофе +250", Quick(25000, "кофе", True)),
        ("250 кофе", Quick(25000, "кофе", None)),  # bare and first: the word names a category
        ("250₽ кофе", Quick(25000, "кофе", None)),
        ("250", Quick(25000, "", None)),
        ("+5000", Quick(500000, "", True)),
        ("вчера такси 300", Quick(30000, "такси", None, days_ago=1)),
        ("позавчера кофе 200", Quick(20000, "кофе", None, days_ago=2)),
        ("вчера 300", Quick(30000, "", None, days_ago=1)),
        ("yesterday taxi 300", Quick(30000, "taxi", None, days_ago=1)),
        ("taxi 4.50", Quick(450, "taxi", None)),
        ("rent 1,200", Quick(120000, "rent", None)),
        ("кофе 5$", OtherCurrency("USD")),
        ("кофе 5 евро", OtherCurrency("EUR")),
        # Not money: a quantity, a time, a date, a plain phrase, too long, nothing.
        ("молоко 2 литра", None),
        ("2 литра молока", None),
        ("3 задачи", None),
        ("30 задач", None),  # bare and first, but the word names no category
        ("12 кг картошки", None),
        ("встреча в 9", None),
        ("встреча 9:30", None),
        ("др маме 12.10", None),
        ("звонок маме", None),
        ("кофе 0", None),
        ("кофе 2000000000", None),
        ("один два три четыре пять шесть семь восемь 100", None),
        ("кофе\n250", None),
        ("вчера", None),
        ("", None),
        ("20 кило картошки", None),
        ("40 бутылок молока", None),
        ("10 утра обед", None),
        ("250 купил кофе", None),
        ("+30 минут", None),
        ("-5 кг", None),
        ("+2 кг", None),
    ],
)
def test_quick_phrases_in_roubles(text: str, expected: Quick | OtherCurrency | None) -> None:
    assert parse_quick(text, "RUB") == expected


def test_a_phrase_in_the_users_own_currency() -> None:
    assert parse_quick("coffee $5", "USD") == Quick(500, "coffee", None)
    assert parse_quick("coffee 5 usd", "USD") == Quick(500, "coffee", None)
    assert parse_quick("кофе 250 ₽", "USD") == OtherCurrency("RUB")


@pytest.mark.parametrize(
    ("note", "key"),
    [
        ("кофе", "cafe"),
        ("капучино с собой", "cafe"),
        ("Пятёрочка", "groceries"),
        ("такси домой", "transport"),
        ("подарок маме", "gifts"),
        ("подарили на др", "gifts_in"),  # the longer stem wins
        ("зп", "salary"),
        ("стипендия", "stipend"),
        ("кэшбэк", "other_in"),
        ("business lunch", "cafe"),  # «bus» is a whole word only
        ("booking", None),
        ("кинопоиск", "subscriptions"),
        ("кино", "fun"),
        ("xyz", None),
        ("", None),
    ],
)
def test_the_words_name_a_category(note: str, key: str | None) -> None:
    assert dictionary_guess(note) == key


def test_the_key_of_a_note() -> None:
    assert note_key("  Кофе, с СОБОЙ! ") == "кофе с собой"
    assert note_key("Ёлка") == "елка"
    assert note_key("a_b") == "a b"


@pytest.mark.parametrize(
    ("hundredths", "currency", "lang", "expected"),
    [
        (25000, "RUB", "ru", f"250{NBSP}₽"),
        (120000, "RUB", "ru", f"1{NBSP}200{NBSP}₽"),
        (43050, "RUB", "ru", f"430,50{NBSP}₽"),
        (120000, "RUB", "en", f"1,200{NBSP}₽"),
        (120000, "USD", "en", "$1,200"),
        (120000, "USD", "ru", f"1{NBSP}200{NBSP}$"),
        (550, "EUR", "en", "€5.50"),
        (25000, "XYZ", "ru", f"250{NBSP}XYZ"),
    ],
)
def test_amounts_in_the_users_currency(
    hundredths: int, currency: str, lang: str, expected: str
) -> None:
    assert format_amount(hundredths, currency, lang) == expected


def test_an_income_is_shown_with_a_plus() -> None:
    assert format_amount(500000, "RUB", "ru", plus=True) == f"+5{NBSP}000{NBSP}₽"
