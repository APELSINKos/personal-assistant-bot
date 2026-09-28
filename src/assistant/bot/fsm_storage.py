"""aiogram FSM storage in SQLite, so an unfinished dialog survives a restart."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.models import FsmState

# DbSession (see middlewares.py) sets this for the lifetime of one update so that an FSM
# write joins the same SQLite write transaction as everything else the handler does.
# SQLite allows only one writer at a time; without sharing the transaction, a handler
# that both saves data and touches FSM state would open a second, independent write
# transaction and deadlock against the still-open one from DbSession ("database is
# locked"). Code that uses SqliteStorage on its own (no middleware, as in its tests)
# sees no ambient session and falls back to a short-lived session per call, exactly as
# before.
current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)


class SqliteStorage(BaseStorage):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @staticmethod
    async def _row(session: AsyncSession, key: StorageKey) -> FsmState | None:
        return await session.get(FsmState, (key.chat_id, key.user_id))

    @staticmethod
    async def _set_state(session: AsyncSession, key: StorageKey, value: str | None) -> None:
        row = await SqliteStorage._row(session, key)
        if row is None:
            if value is None:
                return
            row = FsmState(chat_id=key.chat_id, user_id=key.user_id, data={})
            session.add(row)
        row.state = value

    @staticmethod
    async def _set_data(session: AsyncSession, key: StorageKey, data: Mapping[str, Any]) -> None:
        row = await SqliteStorage._row(session, key)
        if row is None:
            if not data:
                return
            row = FsmState(chat_id=key.chat_id, user_id=key.user_id, state=None)
            session.add(row)
        row.data = dict(data)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        session = current_session.get()
        if session is not None:
            await self._set_state(session, key, value)
            await session.flush()
            return
        async with self._sessionmaker() as session:
            await self._set_state(session, key, value)
            await session.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        session = current_session.get()
        if session is not None:
            row = await self._row(session, key)
            return row.state if row else None
        async with self._sessionmaker() as session:
            row = await self._row(session, key)
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        session = current_session.get()
        if session is not None:
            await self._set_data(session, key, data)
            await session.flush()
            return
        async with self._sessionmaker() as session:
            await self._set_data(session, key, data)
            await session.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        session = current_session.get()
        if session is not None:
            row = await self._row(session, key)
            return dict(row.data) if row and row.data else {}
        async with self._sessionmaker() as session:
            row = await self._row(session, key)
            return dict(row.data) if row and row.data else {}

    async def close(self) -> None:
        return None
