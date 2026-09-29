from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update

from assistant.bot.app import build_dispatcher
from assistant.bot.db_commit import install_commit_before_request
from assistant.core.config import Settings
from tests.bot.fakes import FakeSession
from tests.stubs import StubCbr, StubMeteo


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
def make_dp(sessionmaker, meteo: StubMeteo, cbr: StubCbr, settings: Settings):
    def _make(sections: Sequence[Router] | None = None) -> Dispatcher:
        return build_dispatcher(sessionmaker, meteo, cbr, settings, sections)

    return _make


@pytest.fixture
def dp(make_dp: Callable[..., Dispatcher]) -> Dispatcher:
    return make_dp()


@pytest.fixture
def feed(dp: Dispatcher, bot: Bot):
    async def _feed(update: Update, dispatcher: Dispatcher | None = None) -> None:
        await (dispatcher or dp).feed_update(bot, update)

    return _feed
