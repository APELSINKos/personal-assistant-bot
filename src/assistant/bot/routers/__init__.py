"""Routers of the bot. Every module exposes create_router() that returns a fresh Router.

Importing a section module also registers its "open section" function in bot.sections.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router

from assistant.bot.routers import habits, notes, rates, reminders, settings, today, weather

SECTION_ROUTERS: list[Callable[[], Router]] = [
    weather.create_router,
    today.create_router,
    rates.create_router,
    notes.create_router,
    reminders.create_router,
    habits.create_router,
    settings.create_router,
]
