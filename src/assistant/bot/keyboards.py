"""Keyboards, callback data and small list helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from pydantic import Field

from assistant.core.i18n import Translator, labels

PAGE_SIZE = 5
# A database id in a button: one out of range (a forged button) does not unpack, so it is
# answered as a stale button instead of failing in the database driver.
Id = Annotated[int, Field(ge=0, lt=2**63)]
MENU_KEYS: tuple[str, ...] = (
    "weather",
    "today",
    "reminders",
    "notes",
    "habits",
    "money",
    "schedule",
    "settings",
)
_ROWS = (
    ("weather", "today"),
    ("reminders", "notes"),
    ("habits", "money"),
    ("schedule", "settings"),
)


# A label of an older menu → the section it opens now (a keyboard already shown keeps it).
OLD_LABELS = {"rates": "money"}


class NoteCb(CallbackData, prefix="n"):
    # A new button gets a new action, never a new field: a field would make every button already
    # in the chats stale. "del", the «🗑 N» of the lists before 2.6, asks first now, as "delask".
    action: str
    id: Id = 0
    page: int = 0


class NoteItemCb(CallbackData, prefix="ni"):
    """An item's button on a note's card. It carries the state to set rather than switching: an
    old card's button never undoes a check made in the app."""

    note: Id
    id: Id
    done: Annotated[int, Field(ge=0, le=1)]  # 1: check the item, 0: uncheck it


class KeepCb(CallbackData, prefix="k"):
    """«📝 В заметки» under a «Не понял» answer. It carries nothing: the note is the message the
    answer replies to, read from the chat, since 500 characters would never fit a button."""


class ReminderCb(CallbackData, prefix="r", sep="|"):
    # A custom separator: `value` carries "HH:MM" time choices, which would otherwise
    # collide with the default ":" separator between packed fields.
    action: str
    id: Id = 0
    page: int = 0
    value: str = ""


class FireCb(CallbackData, prefix="f"):
    """A button under a delivered reminder: snooze or done."""

    action: str
    id: Id
    at: int  # the reported firing, in minutes since the epoch


class HabitCb(CallbackData, prefix="h"):
    action: str
    id: Id = 0
    value: str = ""


class ScheduleCb(CallbackData, prefix="sc"):
    action: str
    value: str = ""  # an ISO date, a group number or alert minutes


class SettingsCb(CallbackData, prefix="s"):
    action: str
    value: str = ""


class CityCb(CallbackData, prefix="c"):
    """«🏙 Города»: the list of the weather's cities, adding one, removing one, the choice
    between namesakes when adding."""

    action: str  # list / add / del / pick
    id: Id = 0  # the city to remove; for pick, the place's number in the search
    # Where «↩️ Назад» leads: s — the settings, w — the weather. The sub-view carries it into
    # each of its buttons, where a forged longer value would not fit in 64 bytes: such a
    # button does not unpack and is answered as a stale one.
    back: Annotated[str, Field(pattern="^[sw]$")] = "s"
    token: str = ""  # for pick, the search the button belongs to


class WeatherCb(CallbackData, prefix="w"):
    """A view of the weather: now, by the hour or the week, of the home city or an extra one.
    No date: a press shows the forecast as of the press."""

    # The city buttons carry the view shown, where a forged longer value would not fit in 64
    # bytes: such a button does not unpack and is answered as a stale one.
    view: Annotated[str, Field(pattern="^(now|hours|week)$")]
    city: Id = 0  # an extra city; 0 is the home city
    new: int = 0  # 1 under the digest and «Мой день»: the view comes as a message of its own


class RatesCb(CallbackData, prefix="x"):
    source: str
    target: str


class MoneyCb(CallbackData, prefix="m"):
    action: str
    id: Id = 0
    page: int = 0
    value: str = ""  # a month «2026-09», a currency code


class EntryCb(CallbackData, prefix="e"):
    """A button under a noted expense or income: its category, undo."""

    action: str
    id: Id  # the entry
    value: Id = 0  # a category id, a kind (0 expense, 1 income) or an emoji's place in the set


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
    for old, key in OLD_LABELS.items():
        if text in labels(f"menu-{old}"):
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


# The views of the weather and the keys of their buttons.
WEATHER_VIEWS = {"now": "button-weather-now", "hours": "button-hours", "week": "button-week"}


def weather_views(
    t: Translator, shown: str, city: int = 0, new: int = 0
) -> list[InlineKeyboardButton]:
    """The buttons of the two views besides `shown`, for the same city: «🕐 По часам» and
    «📅 Неделя» under «🌤 Погода», the digest and «Мой день»."""
    return [
        InlineKeyboardButton(
            text=t(key), callback_data=WeatherCb(view=view, city=city, new=new).pack()
        )
        for view, key in WEATHER_VIEWS.items()
        if view != shown
    ]


def today_markup(
    t: Translator, weather: bool, url: str | None = None
) -> InlineKeyboardMarkup | None:
    """The buttons under «Мой день» and the morning digest: when the weather is shown, the home
    city's hours and week, each as a message of its own that leaves this one whole; below them
    the app, when it has an address."""
    rows = [weather_views(t, "now", new=1)] if weather else []
    app = app_markup(t, url)
    if app is not None:
        rows += app.inline_keyboard
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


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
