"""Routers of the bot. Every module exposes create_router() that returns a fresh Router.

Importing a section module also registers its "open section" function in bot.sections.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router

from assistant.bot.routers import rates, today, weather

SECTION_ROUTERS: list[Callable[[], Router]] = [
    weather.create_router,
    today.create_router,
    rates.create_router,
]
