from __future__ import annotations

import os

# Settings require a token; tests never talk to Telegram.
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-UNIT-TESTS-ONLY")

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.models import Base, User


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(db_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s


@pytest.fixture
def make_user(session: AsyncSession) -> Callable[..., Awaitable[User]]:
    async def factory(id: int = 1, tz: str = "Europe/Moscow", **fields: Any) -> User:
        values: dict[str, Any] = {
            "id": id,
            "first_name": "Test",
            "tg_language": "ru",
            "city": "Москва",
            "lat": 55.75,
            "lon": 37.62,
            "timezone": tz,
            "morning_enabled": True,
            "morning_time": "08:00",
        }
        values.update(fields)
        user = User(**values)
        session.add(user)
        await session.commit()
        return user

    return factory
