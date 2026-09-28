"""Registry of the functions that open a section; used by the main menu and by buttons."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram.types import Message

from assistant.bot.context import Ctx

ShowFn = Callable[[Message, Ctx], Awaitable[None]]
SECTIONS: dict[str, ShowFn] = {}


def section(key: str) -> Callable[[ShowFn], ShowFn]:
    def register(func: ShowFn) -> ShowFn:
        SECTIONS[key] = func
        return func

    return register
