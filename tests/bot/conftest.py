from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update

from assistant.bot.app import build_dispatcher
from assistant.bot.db_commit import install_commit_before_request
from assistant.core.config import Settings
from assistant.core.ratelimit import RateLimiter
from assistant.core.services import schedule
from tests.bot.fakes import FakeSession
from tests.stubs import StubCalendars, StubCbr, StubMeteo


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, bot_token="123456:TEST-TOKEN")


@pytest.fixture
def fake() -> FakeSession:
    return FakeSession()


@pytest.fixture
async def bot(fake: FakeSession) -> AsyncIterator[Bot]:
    bot = Bot("123456:TEST-TOKEN", session=fake)
    install_commit_before_request(bot)
    yield bot


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
def monotonic() -> list[float]:
    """The clock of the download and parse budget, in seconds; a test moves it by hand."""
    return [0.0]


@pytest.fixture
def attempts(monotonic: list[float]) -> RateLimiter:
    return schedule.attempt_limiter(lambda: monotonic[0])


@pytest.fixture
def make_dp(
    sessionmaker,
    meteo: StubMeteo,
    cbr: StubCbr,
    calendars: StubCalendars,
    settings: Settings,
    attempts: RateLimiter,
):
    def _make(sections: Sequence[Router] | None = None) -> Dispatcher:
        return build_dispatcher(
            sessionmaker,
            meteo,
            cbr,
            settings,
            sections,
            calendars=calendars,
            attempts=attempts,
        )

    return _make


@pytest.fixture
def dp(make_dp: Callable[..., Dispatcher]) -> Dispatcher:
    return make_dp()


@pytest.fixture
def feed(dp: Dispatcher, bot: Bot):
    async def _feed(update: Update, dispatcher: Dispatcher | None = None) -> None:
        await (dispatcher or dp).feed_update(bot, update)

    return _feed
