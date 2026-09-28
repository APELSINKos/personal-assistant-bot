"""Routers of the bot. Every module exposes create_router() that returns a fresh Router."""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router

SECTION_ROUTERS: list[Callable[[], Router]] = []
