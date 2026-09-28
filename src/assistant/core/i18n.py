"""Fluent translations for the bot, language resolution and locale-aware formatting."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from babel.dates import format_date
from babel.numbers import format_decimal
from fluent.runtime import FluentLocalization, FluentResourceLoader

SUPPORTED: tuple[str, ...] = ("ru", "en")
_RU_FAMILY = frozenset({"ru", "uk", "be", "kk"})
LOCALES_DIR = Path(__file__).resolve().parents[3] / "locales"


def resolve_language(user_language: str | None, tg_language_code: str | None) -> str:
    if user_language in SUPPORTED:
        return user_language
    base = (tg_language_code or "").lower().split("-")[0]
    return "ru" if base in _RU_FAMILY else "en"


class Translator:
    def __init__(self, lang: str, localization: FluentLocalization) -> None:
        self.lang = lang
        self._localization = localization

    def __call__(self, key: str, **args: object) -> str:
        return str(self._localization.format_value(key, args))


@lru_cache(maxsize=len(SUPPORTED))
def translator(lang: str) -> Translator:
    loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}"))
    localization = FluentLocalization([lang], ["bot.ftl"], loader, use_isolating=False)
    return Translator(lang, localization)


def labels(key: str) -> frozenset[str]:
    return frozenset(translator(lang)(key) for lang in SUPPORTED)


def format_day(day: date, lang: str) -> str:
    return str(format_date(day, "d MMMM" if lang == "ru" else "MMMM d", locale=lang))


def format_weekday(day: date, lang: str) -> str:
    return str(format_date(day, "EEEE", locale=lang))


def format_short_day(day: date, lang: str) -> str:
    return str(format_date(day, "EEE, d MMM", locale=lang))


def format_number(value: float, lang: str, digits: int = 2) -> str:
    pattern = "#,##0." + "0" * digits if digits else "#,##0"
    result = str(format_decimal(value, format=pattern, locale=lang))
    return result.replace("\xa0", " ")
