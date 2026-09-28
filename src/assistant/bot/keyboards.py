"""Keyboards, callback data and small list helpers."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from assistant.core.i18n import Translator, labels

PAGE_SIZE = 5
MENU_KEYS: tuple[str, ...] = (
    "weather",
    "today",
    "reminders",
    "notes",
    "habits",
    "rates",
    "settings",
)
_ROWS = (("weather", "today"), ("reminders", "notes"), ("habits", "rates"), ("settings",))


class NoteCb(CallbackData, prefix="n"):
    action: str
    id: int = 0
    page: int = 0


class ReminderCb(CallbackData, prefix="r"):
    action: str
    id: int = 0
    page: int = 0


class HabitCb(CallbackData, prefix="h"):
    action: str
    id: int = 0
    value: str = ""


class SettingsCb(CallbackData, prefix="s"):
    action: str
    value: str = ""


class RatesCb(CallbackData, prefix="x"):
    source: str
    target: str


def main_menu(t: Translator) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=t(f"menu-{key}")) for key in row] for row in _ROWS]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def cancel_menu(t: Translator) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("menu-cancel"))]], resize_keyboard=True
    )


def menu_key(text: str | None) -> str | None:
    if not text:
        return None
    for key in MENU_KEYS:
        if text in labels(f"menu-{key}"):
            return key
    return None


def is_cancel(text: str | None) -> bool:
    return text is not None and text in labels("menu-cancel")


def preview(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def paginate[T](
    items: Sequence[T],
    page: int,
    per_page: int = PAGE_SIZE,
) -> tuple[list[T], int, int]:
    pages = max((len(items) + per_page - 1) // per_page, 1)
    page = min(max(page, 0), pages - 1)
    return list(items[page * per_page : (page + 1) * per_page]), page, pages


def app_markup(t: Translator, url: str | None) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    button = InlineKeyboardButton(text=t("open-app"), web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
