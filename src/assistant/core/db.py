"""Async SQLAlchemy engine for SQLite with pragmas suitable for two processes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_PRAGMAS = ("journal_mode=WAL", "busy_timeout=5000", "synchronous=NORMAL")


def create_engine(url: str, *, foreign_keys: bool = True) -> AsyncEngine:
    """foreign_keys=False is for migrations only: a batch table rebuild drops the old table,
    and with foreign keys on, that DROP would fire ON DELETE CASCADE on every child table."""
    engine = create_async_engine(url)
    if url.startswith("sqlite"):
        pragmas = (*_PRAGMAS, "foreign_keys=ON" if foreign_keys else "foreign_keys=OFF")

        @event.listens_for(engine.sync_engine, "connect")
        def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            for pragma in pragmas:
                cursor.execute(f"PRAGMA {pragma}")
            cursor.close()

    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
