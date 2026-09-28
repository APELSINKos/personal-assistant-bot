from __future__ import annotations

from aiogram.methods import (
    GetMyDescription,
    GetMyName,
    GetMyShortDescription,
    SetChatMenuButton,
    SetMyCommands,
    SetMyDescription,
    SetMyName,
)
from aiogram.types import BotDescription, BotName, BotShortDescription, MenuButtonDefault

from assistant.bot.setup import configure


async def test_configure_changes_only_what_differs(bot, fake, settings) -> None:
    fake.results[GetMyName] = BotName(name="Личный помощник")
    fake.results[GetMyShortDescription] = BotShortDescription(short_description="old")
    fake.results[GetMyDescription] = BotDescription(description="old")
    await configure(bot, settings)
    assert [c.language_code for c in fake.of(SetMyCommands)] == ["ru", "en", None]
    assert [c.language_code for c in fake.of(SetMyName)] == ["en", None]
    assert len(fake.of(SetMyDescription)) == 3
    [menu] = fake.of(SetChatMenuButton)
    assert isinstance(menu.menu_button, MenuButtonDefault)
