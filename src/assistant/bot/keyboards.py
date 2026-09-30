"""Keyboards, callback data and small list helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

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


class ReminderCb(CallbackData, prefix="r", sep="|"):
    # A custom separator: `value` carries "HH:MM" time choices, which would otherwise
    # collide with the default ":" separator between packed fields.
    action: str
    id: int = 0
    page: int = 0
    value: str = ""


class FireCb(CallbackData, prefix="f"):
    """A button under a delivered reminder: snooze or done."""

    action: str
    id: int
    at: int  # the reported firing, in minutes since the epoch


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


def page_buttons(
    t: Translator,
    page: int,
    pages: int,
    pack: Callable[[int], str],
) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text=t("prev"), callback_data=pack(page - 1)))
    if page < pages - 1:
        buttons.append(InlineKeyboardButton(text=t("next"), callback_data=pack(page + 1)))
    return buttons


def app_markup(t: Translator, url: str | None) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    button = InlineKeyboardButton(text=t("open-app"), web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def card_markup(t: Translator, card: int) -> InlineKeyboardMarkup:
    """`card` ties every button to the draft that was current when it was sent."""

    def button(key: str, action: str) -> InlineKeyboardButton:
        data = ReminderCb(action=action, id=card).pack()
        return InlineKeyboardButton(text=t(key), callback_data=data)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("button-create", "ok")],
            [button("button-retime", "retime"), button("button-card-cancel", "no")],
        ]
    )


def time_choices(t: Translator, card: int) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text=hhmm, callback_data=ReminderCb(action="t", id=card, value=hhmm).pack()
        )
        for hhmm in ("09:00", "12:00", "18:00")
    ]
    cancel = InlineKeyboardButton(
        text=t("button-card-cancel"), callback_data=ReminderCb(action="no", id=card).pack()
    )
    return InlineKeyboardMarkup(inline_keyboard=[row, [cancel]])


def fired_markup(t: Translator, reminder_id: int, fired_at: datetime) -> InlineKeyboardMarkup:
    at = int(fired_at.timestamp() // 60)

    def button(key: str, action: str) -> InlineKeyboardButton:
        data = FireCb(action=action, id=reminder_id, at=at).pack()
        return InlineKeyboardButton(text=t(key), callback_data=data)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button("button-snooze-10m", "10m"),
                button("button-snooze-1h", "1h"),
                button("button-snooze-tomorrow", "tomorrow"),
            ],
            [button("button-done", "done")],
        ]
    )
