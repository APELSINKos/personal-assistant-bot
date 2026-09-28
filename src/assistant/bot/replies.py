"""Answering pressed inline buttons: send a new message or edit the one with the button."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup

log = logging.getLogger(__name__)
Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | None


async def send(bot: Bot, query: CallbackQuery, text: str, markup: Markup = None) -> None:
    # Private chats only, so the chat id equals the user id.
    await bot.send_message(query.from_user.id, text, reply_markup=markup)


async def edit(
    bot: Bot,
    query: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    if query.message is None:
        await send(bot, query, text, markup)
        return
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            reply_markup=markup,
        )
    except TelegramBadRequest as error:
        if "message is not modified" in error.message:
            return
        log.info("could not edit a message, sending a new one: %s", error.message)
        await send(bot, query, text, markup)
