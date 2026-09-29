"""Fluent translations for the bot, language resolution and locale-aware formatting."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from babel.dates import format_date, get_day_names
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


def check_translations() -> None:
    """Fail fast at startup: without the locale files Fluent would show raw keys to users."""
    for lang in SUPPORTED:
        if translator(lang)("menu-weather") == "menu-weather":
            raise RuntimeError(f"translations for {lang!r} are missing in {LOCALES_DIR}")


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
    return str(format_decimal(value, format=pattern, locale=lang))


def weekday_short(index: int, lang: str) -> str:
    """0 = Monday: «пн» / «Mon»."""
    return str(get_day_names("abbreviated", locale=lang)[index])
