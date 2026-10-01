from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from assistant.api.app import create_app
from assistant.api.auth import sign_init_data
from assistant.api.ratelimit import RateLimiter
from assistant.core.config import Settings
from tests.stubs import StubCalendars, StubCbr, StubMeteo

TOKEN = "123456:API-TEST-TOKEN"
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow, a Monday


def make_init_data(
    user_id: int = 1,
    *,
    first_name: str = "Alex",
    lang: str | None = "ru",
    signed_at: datetime = NOW,
    token: str = TOKEN,
    extra: dict[str, str] | None = None,
    user_extra: dict[str, Any] | None = None,
) -> str:
    user: dict[str, Any] = {"id": user_id, "first_name": first_name}
    if lang is not None:
        user["language_code"] = lang
    user.update(user_extra or {})
    fields = {
        "auth_date": str(int(signed_at.timestamp())),
        "query_id": "q1",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    fields.update(extra or {})
    return sign_init_data(fields, token)


@pytest.fixture
def api_settings() -> Settings:
    return Settings(_env_file=None, bot_token=TOKEN)


@pytest.fixture
def meteo() -> StubMeteo:
    return StubMeteo()


@pytest.fixture
def cbr() -> StubCbr:
    return StubCbr()


@pytest.fixture
def calendars() -> StubCalendars:
    return StubCalendars()


@pytest.fixture
def clock() -> list[datetime]:
    return [NOW]


@pytest.fixture
def app(sessionmaker, api_settings, meteo, cbr, calendars, clock) -> FastAPI:
    return create_app(
        settings=api_settings,
        sessionmaker=sessionmaker,
        meteo=meteo,
        cbr=cbr,
        calendars=calendars,
        commit="0" * 40,
        clock=lambda: clock[0],
        limiter=RateLimiter(5_000),
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def auth() -> Callable[..., dict[str, str]]:
    def headers(user_id: int = 1, **kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"tma {make_init_data(user_id, **kwargs)}"}

    return headers
