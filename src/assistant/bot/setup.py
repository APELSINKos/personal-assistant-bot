"""Commands, name, descriptions and the menu button in every supported language."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import AiogramError
from aiogram.types import BotCommand, MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from assistant.core.config import Settings
from assistant.core.i18n import SUPPORTED, translator

log = logging.getLogger(__name__)
COMMANDS = ("start", "app", "settings", "help", "cancel")
# Seconds per request: one that hangs must not use up all the time the profile gets in the
# background (CONFIGURE_TIMEOUT in bot/__main__.py).
REQUEST_TIMEOUT = 10


async def _profile(bot: Bot, lang: str | None) -> None:
    t = translator(lang or "en")
    commands = [BotCommand(command=c, description=t(f"cmd-{c}")) for c in COMMANDS]
    current = await bot.get_my_commands(language_code=lang, request_timeout=REQUEST_TIMEOUT)
    if [(c.command, c.description) for c in current] != [
        (c.command, c.description) for c in commands
    ]:
        await bot.set_my_commands(commands, language_code=lang, request_timeout=REQUEST_TIMEOUT)
    name = await bot.get_my_name(language_code=lang, request_timeout=REQUEST_TIMEOUT)
    if name.name != t("bot-name"):
        await bot.set_my_name(
            name=t("bot-name"), language_code=lang, request_timeout=REQUEST_TIMEOUT
        )
    short = t("bot-short-description")
    current_short = await bot.get_my_short_description(
        language_code=lang, request_timeout=REQUEST_TIMEOUT
    )
    if current_short.short_description != short:
        await bot.set_my_short_description(
            short_description=short, language_code=lang, request_timeout=REQUEST_TIMEOUT
        )
    description = t("bot-description")
    current_description = await bot.get_my_description(
        language_code=lang, request_timeout=REQUEST_TIMEOUT
    )
    if current_description.description != description:
        await bot.set_my_description(
            description=description, language_code=lang, request_timeout=REQUEST_TIMEOUT
        )


async def configure(bot: Bot, settings: Settings) -> None:
    # AiogramError, not only TelegramAPIError: an HTML 502 page (ClientDecodeError) or a
    # network failure while starting up must cost a warning, never the process.
    for lang in (*SUPPORTED, None):
        try:
            await _profile(bot, lang)
        except AiogramError as error:
            log.warning("could not update the bot profile for %s: %s", lang or "default", error)
    button: MenuButtonWebApp | MenuButtonDefault
    try:
        if settings.webapp_url:
            button = MenuButtonWebApp(
                text=translator("ru")("menu-button"), web_app=WebAppInfo(url=settings.webapp_url)
            )
        else:
            button = MenuButtonDefault()
        await bot.set_chat_menu_button(menu_button=button, request_timeout=REQUEST_TIMEOUT)
    except AiogramError as error:
        log.warning("could not set the menu button: %s", error)
