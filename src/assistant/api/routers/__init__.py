"""API routers, included under /api in this order."""

from __future__ import annotations

from fastapi import APIRouter

from assistant.api.routers import agenda, habits, health, me, notes, reminders, today

ALL: list[APIRouter] = [
    health.router,
    me.router,
    today.router,
    notes.router,
    reminders.router,
    habits.router,
    agenda.router,
]
