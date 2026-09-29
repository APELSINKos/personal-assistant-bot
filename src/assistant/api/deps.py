"""Request dependencies: application state, a DB session, the verified Telegram user."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.api.auth import AuthError, verify_init_data
from assistant.api.errors import RateLimited
from assistant.api.state import AppState
from assistant.core.models import User
from assistant.core.services import users


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.assistant
    return state


State = Annotated[AppState, Depends(_state)]


async def _session(state: State) -> AsyncIterator[AsyncSession]:
    # Handlers commit their own writes; whatever is left uncommitted is rolled back here.
    async with state.sessionmaker() as db:
        yield db


Session = Annotated[AsyncSession, Depends(_session)]


async def _current_user(
    state: State,
    db: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data.strip():
        raise AuthError("invalid_init_data")
    telegram_user = verify_init_data(
        init_data.strip(), state.settings.bot_token.get_secret_value(), state.clock()
    )
    wait = state.limiter.check(telegram_user.id)
    if wait is not None:
        raise RateLimited(wait)
    user = await users.ensure(
        db, telegram_user.id, telegram_user.first_name, telegram_user.language_code
    )
    # Release SQLite's write lock before a handler waits for Open-Meteo or the Bank of Russia.
    await db.commit()
    return user


CurrentUser = Annotated[User, Depends(_current_user)]

# An item id in a path: SQLite keeps signed 64-bit integers, a larger one would crash the driver.
ItemId = Annotated[int, Path(ge=1, le=2**63 - 1)]
