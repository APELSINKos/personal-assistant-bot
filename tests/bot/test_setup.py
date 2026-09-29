from __future__ import annotations

import logging

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
from assistant.bot.setup import COMMANDS, REQUEST_TIMEOUT, configure
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
