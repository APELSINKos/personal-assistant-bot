from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fluent.syntax import FluentParser, ast

from assistant.core import i18n

LOCALES = Path(__file__).resolve().parents[2] / "locales"


def _keys(lang: str) -> set[str]:
    resource = FluentParser().parse((LOCALES / lang / "bot.ftl").read_text(encoding="utf-8"))
    junk = [entry for entry in resource.body if isinstance(entry, ast.Junk)]
    assert not junk, f"syntax errors in {lang}/bot.ftl: {junk[0].annotations}"
    return {entry.id.name for entry in resource.body if isinstance(entry, ast.Message)}


def test_every_key_exists_in_every_language() -> None:
    assert _keys("ru") == _keys("en")


@pytest.mark.parametrize(
    ("user_lang", "tg_code", "expected"),
    [
        ("en", "ru", "en"),
        ("ru", "en", "ru"),
        (None, "ru", "ru"),
        (None, "uk", "ru"),
        (None, "be", "ru"),
        (None, "kk", "ru"),
        (None, "en-US", "en"),
        (None, "de", "en"),
        (None, None, "en"),
        ("xx", "ru", "ru"),
    ],
)
def test_resolve_language(user_lang: str | None, tg_code: str | None, expected: str) -> None:
    assert i18n.resolve_language(user_lang, tg_code) == expected


@pytest.mark.parametrize(
    ("count", "ru", "en"),
    [
        (1, "1 день", "1 day"),
        (2, "2 дня", "2 days"),
        (5, "5 дней", "5 days"),
        (11, "11 дней", "11 days"),
        (21, "21 день", "21 days"),
        (0, "0 дней", "0 days"),
    ],
)
def test_plural_days(count: int, ru: str, en: str) -> None:
    assert i18n.translator("ru")("days", count=count) == ru
    assert i18n.translator("en")("days", count=count) == en


def test_no_bidi_isolation_marks() -> None:
    text = i18n.translator("ru")("days", count=3)
    assert "⁨" not in text and "⁩" not in text


def test_labels_cover_both_languages() -> None:
    assert i18n.labels("menu-weather") == {"🌤 Погода", "🌤 Weather"}


def test_dates() -> None:
    day = date(2026, 9, 27)
    assert i18n.format_day(day, "ru") == "27 сентября"
    assert i18n.format_day(day, "en") == "September 27"
    assert i18n.format_weekday(day, "ru") == "воскресенье"
    assert i18n.format_weekday(day, "en") == "Sunday"


def test_numbers() -> None:
    assert i18n.format_number(1500.5, "ru") == "1\xa0500,50"
    assert i18n.format_number(1500.5, "en") == "1,500.50"


def test_tip_plurals_ru() -> None:
    t = i18n.translator("ru")
    rain = t("tip-precip-soon", kind="rain", minutes=45)
    snow = t("tip-precip-soon", kind="snow", minutes=21)
    assert rain == "🌧 Через 45 минут дождь — возьми зонт"
    assert snow == "🌨 Через 21 минуту снег — надень капюшон"
