from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import LinkPreviewOptions

from assistant.bot import replies
from tests.bot.fakes import callback_update


def _query():
    query = callback_update("n:page:0:0").callback_query
    assert query is not None
    return query


def test_no_preview_turns_link_previews_off() -> None:
    assert LinkPreviewOptions(is_disabled=True) == replies.NO_PREVIEW


async def test_send_and_edit_pass_the_link_preview_options(bot, fake) -> None:
    await replies.send(bot, _query(), "new", link_preview_options=replies.NO_PREVIEW)
    await replies.edit(bot, _query(), "edited", link_preview_options=replies.NO_PREVIEW)
    sent, edited = fake.calls
    assert isinstance(sent, SendMessage) and isinstance(edited, EditMessageText)
    assert sent.link_preview_options == edited.link_preview_options == replies.NO_PREVIEW


async def test_without_the_options_telegram_shows_previews_as_before(bot, fake) -> None:
    await replies.send(bot, _query(), "new")
    await replies.edit(bot, _query(), "edited")
    assert [call.link_preview_options for call in fake.calls] == [None, None]


async def test_a_new_message_instead_of_an_edit_keeps_the_options(bot, fake) -> None:
    fake.errors.append(
        TelegramBadRequest(
            method=EditMessageText(text="x"), message="Bad Request: message can't be edited"
        )
    )
    await replies.edit(bot, _query(), "fresh", link_preview_options=replies.NO_PREVIEW)
    fresh = fake.calls[-1]
    assert isinstance(fresh, SendMessage) and fresh.link_preview_options == replies.NO_PREVIEW


async def test_a_query_without_its_message_gets_a_new_one_with_the_options(bot, fake) -> None:
    query = _query().model_copy(update={"message": None})
    await replies.edit(bot, query, "fresh", link_preview_options=replies.NO_PREVIEW)
    [fresh] = fake.calls
    assert isinstance(fresh, SendMessage) and fresh.link_preview_options == replies.NO_PREVIEW


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
