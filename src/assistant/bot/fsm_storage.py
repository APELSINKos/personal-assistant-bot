"""aiogram FSM storage in SQLite, so an unfinished dialog survives a restart."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.models import FsmState

# DbSession (see middlewares.py) sets this for the lifetime of one update, so an FSM read
# or write can reuse that session instead of opening a second connection to the same
# SQLite file (a second, independent write would otherwise contend for SQLite's single
# write lock against DbSession's still-open one and deadlock). Every call through this
# module commits immediately (see `_session` below) instead of waiting for DbSession's
# own end-of-update commit, so the write lock is never held across whatever the handler
# awaits next — including the Telegram send that normally follows (see also
# db_commit.py, which commits before any outgoing API call for the same reason). This
# trades strict whole-update atomicity for never holding the lock longer than one FSM
# call. Code that uses SqliteStorage on its own (no middleware, as in its tests) sees no
# ambient session and falls back to a short-lived session per call.
current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)


class SqliteStorage(BaseStorage):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session to read or mutate FSM state through, and commit when done."""
        session = current_session.get()
        if session is not None:
            yield session
            await session.commit()
            return
        async with self._sessionmaker() as session:
            yield session
            await session.commit()

    @staticmethod
    async def _row(session: AsyncSession, key: StorageKey) -> FsmState | None:
        return await session.get(FsmState, (key.chat_id, key.user_id))

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with self._session() as session:
            row = await self._row(session, key)
            if row is None:
                if value is None:
                    return
                row = FsmState(chat_id=key.chat_id, user_id=key.user_id, data={})
                session.add(row)
            row.state = value

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._session() as session:
            row = await self._row(session, key)
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with self._session() as session:
            row = await self._row(session, key)
            if row is None:
                if not data:
                    return
                row = FsmState(chat_id=key.chat_id, user_id=key.user_id, state=None)
                session.add(row)
            row.data = dict(data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._session() as session:
            row = await self._row(session, key)
            return dict(row.data) if row and row.data else {}

    async def close(self) -> None:
        return None
