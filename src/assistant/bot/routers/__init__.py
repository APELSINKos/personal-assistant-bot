"""Routers of the bot. Every module exposes create_router() that returns a fresh Router.

Importing a section module also registers its "open section" function in bot.sections.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router

from assistant.bot.routers import (
    habits,
    money,
    money_entry,
    notes,
    rates,
    reminders,
    schedule,
    settings,
    today,
    weather,
)

SECTION_ROUTERS: list[Callable[[], Router]] = [
    weather.create_router,
    today.create_router,
    rates.create_router,
    notes.create_router,
    reminders.create_router,
    habits.create_router,
    schedule.create_router,
    settings.create_router,
    money.create_router,
    money_entry.create_router,  # after reminders: a phrase with a time is a reminder
]
