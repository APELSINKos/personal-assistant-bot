"""Commands, name, descriptions and the menu button in every supported language."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from assistant.core.config import Settings
from assistant.core.i18n import SUPPORTED, translator

log = logging.getLogger(__name__)
COMMANDS = ("start", "app", "settings", "help", "cancel")


async def _profile(bot: Bot, lang: str | None) -> None:
    t = translator(lang or "en")
    commands = [BotCommand(command=c, description=t(f"cmd-{c}")) for c in COMMANDS]
    await bot.set_my_commands(commands, language_code=lang)
    if (await bot.get_my_name(language_code=lang)).name != t("bot-name"):
        await bot.set_my_name(name=t("bot-name"), language_code=lang)
    short = t("bot-short-description")
    if (await bot.get_my_short_description(language_code=lang)).short_description != short:
        await bot.set_my_short_description(short_description=short, language_code=lang)
    description = t("bot-description")
    if (await bot.get_my_description(language_code=lang)).description != description:
        await bot.set_my_description(description=description, language_code=lang)


async def configure(bot: Bot, settings: Settings) -> None:
    for lang in (*SUPPORTED, None):
        try:
            await _profile(bot, lang)
        except TelegramAPIError as error:
            log.warning("could not update the bot profile for %s: %s", lang or "default", error)
    try:
        if settings.webapp_url:
            button = MenuButtonWebApp(
                text=translator("ru")("menu-button"), web_app=WebAppInfo(url=settings.webapp_url)
            )
            await bot.set_chat_menu_button(menu_button=button)
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except TelegramAPIError as error:
        log.warning("could not set the menu button: %s", error)
