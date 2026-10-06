from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from aiogram import Bot
from aiogram.exceptions import ClientDecodeError, TelegramNetworkError
from aiogram.methods import (
    GetMyCommands,
    GetMyDescription,
    GetMyName,
    GetMyShortDescription,
    SetChatMenuButton,
    SetMyCommands,
    SetMyDescription,
    SetMyName,
)
from aiogram.types import (
    BotCommand,
    BotDescription,
    BotName,
    BotShortDescription,
    MenuButtonDefault,
)

from assistant import __version__
from assistant.bot import __main__ as entry
from assistant.bot.setup import COMMANDS, REQUEST_TIMEOUT, configure
from assistant.core.config import Settings
from assistant.core.i18n import translator


def _commands(lang: str) -> list[BotCommand]:
    t = translator(lang)
    return [BotCommand(command=c, description=t(f"cmd-{c}")) for c in COMMANDS]


async def test_configure_changes_only_what_differs(bot, fake, settings) -> None:
    fake.results[GetMyCommands] = _commands("ru")
    fake.results[GetMyName] = BotName(name="Личный помощник")
    fake.results[GetMyShortDescription] = BotShortDescription(short_description="old")
    fake.results[GetMyDescription] = BotDescription(description="old")
    await configure(bot, settings)
    # Only the languages whose commands differ from Telegram's are set (spec 7.2).
    assert [c.language_code for c in fake.of(SetMyCommands)] == ["en", None]
    assert [c.language_code for c in fake.of(SetMyName)] == ["en", None]
    assert len(fake.of(SetMyDescription)) == 3
    [menu] = fake.of(SetChatMenuButton)
    assert isinstance(menu.menu_button, MenuButtonDefault)
    assert set(fake.timeouts) == {REQUEST_TIMEOUT}


async def test_configure_survives_html_502_and_network_errors(bot, fake, settings) -> None:
    fake.results[GetMyCommands] = _commands("en")
    fake.results[GetMyName] = BotName(name="Personal assistant")
    fake.results[GetMyShortDescription] = BotShortDescription(short_description="old")
    fake.results[GetMyDescription] = BotDescription(description="old")
    fake.errors += [
        ClientDecodeError("failed to decode", ValueError("not json"), b"<html>502</html>"),
        TelegramNetworkError(method=GetMyCommands(), message="timeout"),
    ]
    await configure(bot, settings)  # must not raise
    # "ru" and "en" failed on their first request; the default profile and the menu button
    # were still set up.
    assert [c.language_code for c in fake.of(GetMyCommands)] == ["ru", "en", None]
    assert len(fake.of(SetChatMenuButton)) == 1


async def test_bot_started_is_logged_when_polling_starts(dp, bot, caplog) -> None:
    caplog.set_level(logging.INFO)
    await dp.emit_startup(bot=bot)
    assert f"Bot started, version {__version__}" in caplog.messages


class Polling:
    """The dispatcher as main() runs it: polling starts, then goes on until the bot stops. Like
    aiogram's, it closes the bot's session as it stops unless told not to."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    def resolve_used_update_types(self) -> list[str]:
        return []

    async def start_polling(
        self, bot: Bot, *, close_bot_session: bool = True, **options: Any
    ) -> None:
        self.started.set()
        try:
            await self.stopped.wait()
        finally:
            if close_bot_session:
                await bot.session.close()


class Idle:
    """The scheduler and the directory crawler, with nothing to do."""

    def __init__(self, *args: Any, **options: Any) -> None:
        pass

    async def run(self) -> None:
        pass

    def stop(self) -> None:
        pass


class Hanging:
    """configure() while Telegram does not answer: it never returns. Cancelled, its request
    takes a moment to end, as a real one does."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.task: asyncio.Task[Any] | None = None

    async def __call__(self, bot: Bot, settings: Settings) -> None:
        self.task = asyncio.current_task()
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.05)


class Failing:
    """configure() with an error that is not one of aiogram's: a bug, say."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.task: asyncio.Task[Any] | None = None

    async def __call__(self, bot: Bot, settings: Settings) -> None:
        self.task = asyncio.current_task()
        self.entered.set()
        raise RuntimeError("not one of aiogram's errors")


@pytest.fixture
def polling(monkeypatch, settings, bot, db_url) -> Polling:
    """main() with the fake Telegram, a test database and idle background work."""
    polling = Polling()
    in_tests = settings.model_copy(update={"database_url": db_url})
    monkeypatch.setattr(entry, "get_settings", lambda: in_tests)
    monkeypatch.setattr(entry, "setup_logging", lambda *args: None)
    monkeypatch.setattr(entry, "create_bot", lambda settings: bot)
    monkeypatch.setattr(entry, "build_dispatcher", lambda *args, **options: polling)
    monkeypatch.setattr(entry, "Scheduler", Idle)
    monkeypatch.setattr(entry, "DirectoryCrawler", Idle)
    return polling


@pytest.fixture
def hanging(monkeypatch) -> Hanging:
    hanging = Hanging()
    monkeypatch.setattr(entry, "configure", hanging)
    return hanging


async def test_polling_starts_while_telegram_keeps_the_profile_waiting(polling, hanging) -> None:
    main = asyncio.create_task(entry.main())
    try:
        await asyncio.wait_for(asyncio.gather(polling.started.wait(), hanging.entered.wait()), 5)
        assert hanging.task is not None and not hanging.task.done()
        polling.stopped.set()  # the bot stops
        # Not wait_for(main): its timeout would cancel main, and whether main stops by itself
        # is the check.
        await asyncio.wait({main}, timeout=5)
        assert main.done()  # the profile was cancelled, not waited for
        await main
        assert hanging.task.cancelled()
    finally:
        main.cancel()  # a failed check leaves no bot running


async def test_a_profile_that_hangs_is_given_up_with_a_warning(
    polling, hanging, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(entry, "CONFIGURE_TIMEOUT", 0.05)
    main = asyncio.create_task(entry.main())
    await asyncio.wait_for(hanging.entered.wait(), 5)
    assert hanging.task is not None
    await asyncio.wait({hanging.task}, timeout=5)
    assert hanging.task.done() and not hanging.task.cancelled()  # it gave up by itself
    assert "the bot profile was not updated in 0.05 s, given up" in caplog.messages
    assert not main.done()  # polling goes on
    polling.stopped.set()
    await asyncio.wait_for(main, 5)


async def test_an_error_in_the_profile_costs_a_log_line_not_polling(
    polling, monkeypatch, caplog
) -> None:
    failing = Failing()
    monkeypatch.setattr(entry, "configure", failing)
    main = asyncio.create_task(entry.main())
    try:
        await asyncio.wait_for(asyncio.gather(polling.started.wait(), failing.entered.wait()), 5)
        assert failing.task is not None
        await asyncio.wait({failing.task}, timeout=5)
        assert failing.task.done() and failing.task.exception() is None  # caught and logged
        line = "could not update the bot profile"
        [logged] = [record for record in caplog.records if record.getMessage() == line]
        assert logged.exc_info is not None and isinstance(logged.exc_info[1], RuntimeError)
        assert not main.done()  # polling goes on
        polling.stopped.set()
        await asyncio.wait({main}, timeout=5)
        assert main.done()
        await main  # and the bot stops cleanly
    finally:
        main.cancel()  # a failed check leaves no bot running


async def test_the_profile_ends_before_its_session_is_closed(
    polling, hanging, fake, monkeypatch
) -> None:
    # Closed under the profile's request, the session would turn the stop into a false error
    # in the log and a new connection for the profile's next language.
    profile_running: list[bool] = []

    async def close() -> None:
        profile_running.append(hanging.task is not None and not hanging.task.done())

    monkeypatch.setattr(fake, "close", close)
    main = asyncio.create_task(entry.main())
    try:
        await asyncio.wait_for(hanging.entered.wait(), 5)
        polling.stopped.set()
        await asyncio.wait({main}, timeout=5)
        assert main.done()
        await main
        assert profile_running == [False]  # closed once, by main(), after the profile ended
    finally:
        main.cancel()
