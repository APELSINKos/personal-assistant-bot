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
        ("1 200", Quick(120000, "", None)),  # one number with a group, not «200» noted «1»
        ("+1 200", Quick(120000, "", True)),
        ("15 000", Quick(1500000, "", None)),
        ("12 345,50", Quick(1234550, "", None)),
        ("1 200 ₽", Quick(120000, "", None)),
        ("вчера 1 200", Quick(120000, "", None, days_ago=1)),
        ("☕ 250", Quick(25000, "☕", None)),  # an emoji is a note
        ("1 000 000", Quick(100000000, "", None)),
        ("250₽ (кофе)", Quick(25000, "(кофе)", None)),
        ("300 руб 3 билета", Quick(30000, "3 билета", None)),
        ("+5000 (стипендия)", Quick(500000, "(стипендия)", True)),
        ("$1 200", OtherCurrency("USD")),  # a sign before a grouped number is one amount
        ("вчера такси 300", Quick(30000, "такси", None, days_ago=1)),
        ("позавчера кофе 200", Quick(20000, "кофе", None, days_ago=2)),
        ("вчера 300", Quick(30000, "", None, days_ago=1)),
        ("yesterday taxi 300", Quick(30000, "taxi", None, days_ago=1)),
        ("taxi 4.50", Quick(450, "taxi", None)),
        ("rent 1,200", Quick(120000, "rent", None)),
        ("кофе 5$", OtherCurrency("USD")),
        ("кофе 5 евро", OtherCurrency("EUR")),
        # Digits in groups that are not a phone number: still money.
        ("маме 8 999", Quick(899900, "маме", None)),  # the shape of «продукты 1 200»
        ("такси 8 500", Quick(850000, "такси", None)),
        ("телефон 500", Quick(50000, "телефон", None)),  # «телефон» names the category
        ("оплатил телефон 500", Quick(50000, "оплатил телефон", None)),
        ("phone 300", Quick(30000, "phone", None)),
        ("телефон 1 200", Quick(120000, "телефон", None)),  # the first group is not 8 or 7
        ("номер 3500", Quick(350000, "номер", None)),
        ("номер в отеле 4500", Quick(450000, "номер в отеле", None)),
        ("автобус 7 45", Quick(4500, "автобус 7", None)),
        ("маршрутка 52 60", Quick(6000, "маршрутка 52", None)),
        ("кофе 2 99", Quick(9900, "кофе 2", None)),
        ("тел 8", Quick(800, "тел", None)),  # one group after a phone word
        ("номер 7", Quick(700, "номер", None)),
        ("phone 8", Quick(800, "phone", None)),
        # A phone word makes the digits a number only right before them.
        ("купил телефон маме 8 999", Quick(899900, "купил телефон маме", None)),
        # A number's tail is 3, 2 and 2 digits, the last without kopecks or a currency.
        ("кофе 12 45 67", Quick(6700, "кофе 12 45", None)),
        ("кофе 1234 45 67", Quick(6700, "кофе 1234 45", None)),
        ("кофе 123 4 67", Quick(6700, "кофе 123 4", None)),
        ("кофе 123 456 78", Quick(7800, "кофе 123 456", None)),
        ("кофе 123 45 6", Quick(600, "кофе 123 45", None)),
        ("кофе 123 45 678", Quick(4567800, "кофе 123", None)),
        ("кофе 123 45 67₽", Quick(6700, "кофе 123 45", None)),
        ("кофе 123 45 67,50", Quick(6750, "кофе 123 45", None)),
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
        ("+7 999 123-45-67", None),  # a phone number
        ("+7 999 1234567", None),
        ("+7 (999) 123-45-67", None),
        ("250 за", None),  # only a connective after the number
        ("8 999 123 45 67", None),
        ("2 + 2 = 4", None),
        # A phone number at the end: its last digits «123 45 67», or a phone word before 8 or 7.
        ("тел 8 999 123 45 67", None),
        ("такси 8 999 123 45 67", None),
        ("тел 123 45 67", None),
        ("позвонить маме 8 999 123 45 67", None),
        ("кофе 250 тел 8 999", None),
        ("кофе 250 тел +7 999", None),  # not an income of 7 999
        ("номер 8 800 555 35 35", None),
        # A phone word before more than two groups, of any length.
        ("тел 8 999 1234567", None),
        ("моб +7 999 123 4567", None),
        # A whole number in the last groups, after any word: 8 or 7 and ten digits, or +7 and ten.
        ("Маша 8 999 1234567", None),
        ("мама +7 916 1234567", None),
        ("Вася 8 999 123 4567", None),
        ("номер: 8 800 2000 600", None),
        ("кофе 250 8 999 1234567", None),
        ("кофе 8 999 1234", Quick(123400, "кофе 8 999", None)),  # eight digits are no number
        # A phone word with a colon.
        ("тел: 8 999", None),
        ("кофе 250 тел: 8 999", None),
        # Every phone word, in any case.
        ("Тел 8 999", None),
        ("кофе 250 ТЕЛ. 8 999", None),
        ("телефон 8 999", None),
        ("номер 7 999", None),
        ("моб 8 912", None),
        ("моб. 8 912", None),
        ("tel 8 999", None),
        ("Phone 8 999", None),
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
        ("премия", "salary"),
        ("премиальные", "salary"),
        ("премиум подписка", "subscriptions"),  # not a bonus
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
