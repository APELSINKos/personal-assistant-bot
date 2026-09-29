"""API routers, included under /api in this order."""

from __future__ import annotations

from fastapi import APIRouter

from assistant.api.routers import health, me

ALL: list[APIRouter] = [health.router, me.router]
