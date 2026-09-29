from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from assistant.bot import replies
from tests.bot.fakes import callback_update


def _query():
    query = callback_update("n:page:0:0").callback_query
    assert query is not None
    return query


async def test_edit_ignores_not_modified(bot, fake) -> None:
    fake.errors.append(
        TelegramBadRequest(
            method=EditMessageText(text="x"), message="Bad Request: message is not modified"
        )
    )
    await replies.edit(bot, _query(), "same text")
    assert len(fake.calls) == 1


async def test_edit_falls_back_to_a_new_message(bot, fake) -> None:
    fake.errors.append(
        TelegramBadRequest(
            method=EditMessageText(text="x"), message="Bad Request: message can't be edited"
        )
    )
    await replies.edit(bot, _query(), "fresh")
    assert isinstance(fake.calls[-1], SendMessage) and fake.calls[-1].text == "fresh"


async def test_answer_quietly_ignores_an_expired_query(bot, fake) -> None:
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await replies.answer_quietly(_query().as_(bot), "🗑 Удалено")  # does not raise
    [answer] = fake.of(AnswerCallbackQuery)
    assert answer.text == "🗑 Удалено"


async def test_answer_quietly_does_not_hide_other_errors(bot, fake) -> None:
    fake.errors.append(
        TelegramNetworkError(method=AnswerCallbackQuery(callback_query_id="1"), message="x")
    )
    with pytest.raises(TelegramNetworkError):
        await replies.answer_quietly(_query().as_(bot))
