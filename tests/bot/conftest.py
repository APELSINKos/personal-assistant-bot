from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from datetime import date
from typing import Any

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update

from assistant.bot.app import build_dispatcher
from assistant.bot.db_commit import install_commit_before_request
from assistant.core.clients.cbr import Rate, Rates
from assistant.core.clients.openmeteo import City
from assistant.core.config import Settings
from assistant.core.errors import UpstreamUnavailable
from tests.bot.fakes import FakeSession


class StubMeteo:
    def __init__(self) -> None:
        self.forecast_data: dict[str, Any] = {
            "current": {
                "time": "2026-09-28T10:00",
                "temperature_2m": 9.6,
                "apparent_temperature": 7.2,
                "weather_code": 1,
                "wind_speed_10m": 3.4,
                "precipitation": 0,
            },
            "daily": {"temperature_2m_max": [13.2], "temperature_2m_min": [5.8]},
        }
        self.cities: list[City] = []
        self.fail = False

    async def forecast(self, lat: float, lon: float) -> dict[str, Any]:
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.forecast_data

    async def search(self, name: str, lang: str, count: int = 5) -> list[City]:
        if self.fail:
            raise UpstreamUnavailable(service="open-meteo")
        return self.cities


class StubCbr:
    def __init__(self) -> None:
        self.fail = False

    async def daily(self) -> Rates:
        if self.fail:
            raise UpstreamUnavailable(service="cbr")
        return Rates(date(2026, 9, 28), Rate(84.1975, -0.3118), Rate(96.6671, -0.8313))


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
