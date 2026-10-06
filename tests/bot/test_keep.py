from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    PhotoSize,
    ReplyParameters,
    Update,
)

from assistant.bot.keyboards import KeepCb, NoteCb, main_menu
from assistant.bot.replies import NO_PREVIEW
from assistant.bot.routers import fallback
from assistant.bot.routers import reminders as reminders_router
from assistant.core.config import LIMITS
from assistant.core.i18n import translator
from assistant.core.services import notes
from tests.bot.fakes import callback_update, message_update, tg_user

CLOCK = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # the bot's clock
SALE = "https://example.com/sale"
HINT = (
    "Чтобы создать напоминание, просто напиши, например: «завтра в 9 купить молоко». "
    "Трату — так: «кофе 250»."
)
KEEP = f"🤔 Не понял. Если это заметка — нажми «📝 В заметки».\n{HINT}"
UNKNOWN = f"🤔 Не понял. Выбери раздел в меню ниже 👇\n{HINT}"
SAVED = "✅ Заметка сохранена."
GONE = "Сообщение уже недоступно"
TOO_LONG = "Слишком длинно для заметки — до 500 символов"
LIMIT = "Достигнут лимит — 50 заметок. Удали лишние."
MENU = main_menu(translator("ru"))
_ids = itertools.count(7000)


@pytest.fixture(autouse=True)
def bot_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fallback, "clock", lambda: CLOCK)


def _message(**fields: Any) -> Message:
    return Message(message_id=next(_ids), date=CLOCK, chat=Chat(id=1, type="private"), **fields)


def said(text: str, *, entities: list[MessageEntity] | None = None, lang: str = "ru") -> Message:
    return _message(from_user=tg_user(1, lang), text=text, entities=entities)


def photo(caption: str | None = None, *, entities: list[MessageEntity] | None = None) -> Message:
    size = PhotoSize(file_id="p", file_unique_id="pu", width=1, height=1)
    return _message(from_user=tg_user(1), photo=[size], caption=caption, caption_entities=entities)


def send(message: Message) -> Update:
    return Update(update_id=next(_ids), message=message)


def press(message: Message | InaccessibleMessage, *, lang: str = "ru") -> Update:
    """«📝 В заметки» pressed under the bot's `message`."""
    query = CallbackQuery(
        id=str(next(_ids)),
        from_user=tg_user(1, lang),
        chat_instance="ci",
        data=KeepCb().pack(),
        message=message,
    )
    return Update(update_id=next(_ids), callback_query=query)


def tap(source: Message | None, *, lang: str = "ru") -> Update:
    """The button under the bot's answer to `source`, as Telegram sends it back: with the message
    the answer replies to as that message is now; None when the user has deleted it."""
    return press(_message(text=KEEP, reply_to_message=source), lang=lang)


def hidden_link(offset: int, length: int) -> list[MessageEntity]:
    return [MessageEntity(type="text_link", offset=offset, length=length, url=SALE)]


def buttons(markup: InlineKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


def data(markup: InlineKeyboardMarkup) -> list[list[str | None]]:
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def last_answer(fake) -> AnswerCallbackQuery:
    return fake.of(AnswerCallbackQuery)[-1]


async def fill(session, count: int) -> None:
    for number in range(count):
        await notes.create(session, 1, f"заметка {number}", now=CLOCK)
    await session.commit()


async def test_words_the_bot_did_not_understand_get_the_button_in_a_reply(feed, fake) -> None:
    source = said("купить молоко")
    await feed(send(source))
    [reply] = fake.of(SendMessage)
    assert reply.text == KEEP
    # One button and no main menu: a message has one keyboard, and the menu stays on the screen.
    assert buttons(reply.reply_markup) == [["📝 В заметки"]]
    assert data(reply.reply_markup) == [["k"]] == [[KeepCb().pack()]]
    # A reply to the message the button saves, sent even if that message is deleted meanwhile.
    assert reply.reply_parameters == ReplyParameters(
        message_id=source.message_id, allow_sending_without_reply=True
    )


async def test_the_button_saves_the_message_it_answered(feed, fake, session) -> None:
    source = said("купить молоко")
    await feed(send(source))
    await feed(tap(source))
    [note] = await notes.list_for(session, 1)
    assert (note.text, note.created_at) == ("купить молоко", CLOCK)  # the bot's clock
    assert last_answer(fake).text is None
    saved = fake.of(EditMessageText)[-1]
    assert saved.text == SAVED
    assert buttons(saved.reply_markup) == [["📝 Открыть"]]
    assert data(saved.reply_markup) == [[NoteCb(action="open", id=note.id).pack()]]
    assert saved.link_preview_options == NO_PREVIEW
    await feed(callback_update(data(saved.reply_markup)[0][0]))  # «📝 Открыть»: its card
    assert fake.of(EditMessageText)[-1].text == "купить молоко"


async def test_hidden_links_are_written_out_from_a_text_or_a_caption(feed, fake, session) -> None:
    # Telegram counts in UTF-16: «🔥» is two units, so «тут» starts at 10.
    text = said("🔥 Скидки тут", entities=hidden_link(10, 3))
    picture = photo("Афиша тут", entities=hidden_link(6, 3))
    for source in (text, picture):
        await feed(send(source))
        assert fake.sent_texts()[-1] == KEEP
        await feed(tap(source))
    assert [note.text for note in await notes.list_for(session, 1)] == [
        f"Афиша тут ({SALE})",
        f"🔥 Скидки тут ({SALE})",
    ]


async def test_a_command_or_a_message_without_words_gets_the_old_answer(feed, fake) -> None:
    for message in (said("/x"), said("/note купить молоко"), photo()):
        await feed(send(message))
    await feed(message_update(None, sticker=True))
    answers = fake.of(SendMessage)
    assert [answer.text for answer in answers] == [UNKNOWN] * 4
    assert all(answer.reply_markup == MENU for answer in answers)
    assert all(answer.reply_parameters is None for answer in answers)


async def test_the_button_needs_words_a_note_can_keep_with_their_links(feed, fake) -> None:
    await feed(send(said("я" * 500)))
    assert fake.sent_texts()[-1] == KEEP
    await feed(send(said("я" * 501)))
    assert fake.sent_texts()[-1] == UNKNOWN
    # 500 characters as sent, past the limit with the address after «тут».
    await feed(send(said("я" * 497 + "тут", entities=hidden_link(497, 3))))
    assert fake.sent_texts()[-1] == UNKNOWN


async def test_no_button_at_the_limit_of_notes(feed, fake, session, make_user) -> None:
    await make_user()
    await fill(session, LIMITS.notes)
    await feed(send(said("купить молоко")))
    [answer] = fake.of(SendMessage)
    assert (answer.text, answer.reply_markup) == (UNKNOWN, MENU)


async def test_a_tap_at_the_limit_keeps_the_button(feed, fake, session, make_user) -> None:
    await make_user()
    await fill(session, LIMITS.notes - 1)
    source = said("купить молоко")
    await feed(send(source))
    assert fake.sent_texts()[-1] == KEEP
    await notes.create(session, 1, "из приложения", now=CLOCK)  # the last place, taken in the app
    await session.commit()
    await feed(tap(source))
    assert (last_answer(fake).text, last_answer(fake).show_alert) == (LIMIT, True)
    assert fake.of(EditMessageReplyMarkup) == [] and fake.of(EditMessageText) == []
    assert await notes.count(session, 1) == LIMITS.notes
    # The button stays for when a note is deleted.
    await notes.delete(session, 1, (await notes.list_for(session, 1))[0].id)
    await session.commit()
    await feed(tap(source))
    assert fake.of(EditMessageText)[-1].text == SAVED
    assert (await notes.list_for(session, 1))[0].text == "купить молоко"


async def test_a_deleted_or_too_old_message_is_gone(feed, fake, session) -> None:
    deleted = tap(None)  # the user deleted the message the answer replied to
    too_old = press(InaccessibleMessage(chat=Chat(id=1, type="private"), message_id=next(_ids)))
    caption_removed = tap(photo())  # the only words, a caption, edited away
    for update in (deleted, too_old, caption_removed):
        await feed(update)
        # A note at the top of the chat, as «Этого уже нет», not a refusal to read and close.
        assert (last_answer(fake).text, last_answer(fake).show_alert) == (GONE, None)
        assert fake.of(EditMessageReplyMarkup)[-1].reply_markup is None  # the button goes
    assert len(fake.of(EditMessageReplyMarkup)) == 3
    assert fake.of(EditMessageText) == []
    assert await notes.count(session, 1) == 0


async def test_a_message_edited_past_the_limit_is_too_long(feed, fake, session) -> None:
    # The button came with a short text, which the user then made longer.
    await feed(tap(said("я" * 497 + "тут", entities=hidden_link(497, 3))))
    assert (last_answer(fake).text, last_answer(fake).show_alert) == (TOO_LONG, True)
    assert fake.of(EditMessageReplyMarkup)[-1].reply_markup is None  # the button goes
    assert fake.of(EditMessageText) == []
    assert await notes.count(session, 1) == 0


async def test_two_taps_in_a_row_save_one_note(feed, fake, session, monkeypatch) -> None:
    source = said("купить молоко")
    await feed(send(source))
    # The user's updates run one at a time: the second tap comes after the first one is done,
    # with the answer as it was, the button still under it.
    await feed(tap(source))
    await feed(tap(source))
    [note] = await notes.list_for(session, 1)
    first, second = fake.of(EditMessageText)
    assert first.text == second.text == SAVED
    assert data(first.reply_markup) == data(second.reply_markup)
    assert data(first.reply_markup) == [[NoteCb(action="open", id=note.id).pack()]]
    # 59 seconds after the note it is the same tap still; at a minute the same words make a note.
    monkeypatch.setattr(fallback, "clock", lambda: CLOCK + timedelta(seconds=59))
    await feed(tap(source))
    assert await notes.count(session, 1) == 1
    monkeypatch.setattr(fallback, "clock", lambda: CLOCK + timedelta(seconds=60))
    await feed(tap(source))
    assert await notes.count(session, 1) == 2


async def test_any_note_with_the_same_words_within_a_minute_is_the_one(feed, fake, session) -> None:
    milk, bread = said("купить молоко"), said("купить хлеб")
    for source in (milk, bread, milk):
        await feed(tap(source))
    listed = await notes.list_for(session, 1)
    assert [note.text for note in listed] == ["купить хлеб", "купить молоко"]
    # The third tap shows the note the first one saved.
    assert data(fake.of(EditMessageText)[-1].reply_markup) == [
        [NoteCb(action="open", id=listed[1].id).pack()]
    ]


async def test_the_newest_note_with_the_same_words_is_the_one(
    feed, fake, session, make_user
) -> None:
    # The same words saved five minutes ago, twice: once pinned (first in the list), once not.
    await make_user()
    for pinned in (True, False):
        await notes.create(
            session, 1, "купить молоко", pinned=pinned, now=CLOCK - timedelta(minutes=5)
        )
    await session.commit()
    source = said("купить молоко")
    await feed(send(source))
    await feed(tap(source))
    await feed(tap(source))
    # The second tap keeps the note the first one made, the newest with these words.
    assert await notes.count(session, 1) == 3
    [new] = [note for note in await notes.list_for(session, 1) if note.created_at == CLOCK]
    opener = [[NoteCb(action="open", id=new.id).pack()]]
    assert [data(edit.reply_markup) for edit in fake.of(EditMessageText)] == [opener, opener]


async def test_an_expired_query_after_the_save_still_shows_it(feed, fake, session) -> None:
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(tap(said("купить молоко")))
    assert fake.sent_texts() == [SAVED]
    assert await notes.count(session, 1) == 1


async def test_in_english(feed, fake, session) -> None:
    source = said("buy milk", lang="en")
    await feed(send(source))
    reply = fake.of(SendMessage)[-1]
    assert reply.text == (
        "🤔 I didn't get that. If it's a note, tap “📝 Save as a note”.\n"
        "To create a reminder, just write, e.g. “tomorrow at 9 buy milk”. "
        "An expense — like this: “coffee 250”."
    )
    assert buttons(reply.reply_markup) == [["📝 Save as a note"]]
    await feed(tap(source, lang="en"))
    saved = fake.of(EditMessageText)[-1]
    assert (saved.text, buttons(saved.reply_markup)) == ("✅ Note saved.", [["📝 Open"]])
    await feed(tap(None, lang="en"))
    assert last_answer(fake).text == "That message is no longer available"
    await feed(tap(said("x" * 501, lang="en"), lang="en"))
    assert last_answer(fake).text == "Too long for a note — up to 500 characters"


async def test_a_dialog_left_behind_answers_with_the_main_menu_and_no_button(
    feed, fake, dp, bot, monkeypatch
) -> None:
    key = StorageKey(bot_id=bot.id, chat_id=1, user_id=1)
    # A state no router handles any more, left by an older release: fallback.orphan_state.
    await dp.storage.set_state(key, "OldForm:gone")
    await feed(send(said("купить молоко")))
    assert await dp.storage.get_state(key) is None
    # A reminder's time prompt left for a day: reminders._no_dialog.
    monkeypatch.setattr(reminders_router, "clock", lambda: CLOCK)
    await feed(message_update("завтра экзамен, волнуюсь"))
    assert await dp.storage.get_state(key) == "ReminderForm:time"
    monkeypatch.setattr(reminders_router, "clock", lambda: CLOCK + timedelta(hours=25))
    await feed(send(said("купить молоко")))
    assert await dp.storage.get_state(key) is None
    # Both may leave «❌ Отмена» on the screen: the main menu brings the menu back.
    orphan, _, left = fake.of(SendMessage)
    for answer in (orphan, left):
        assert (answer.text, answer.reply_markup, answer.reply_parameters) == (UNKNOWN, MENU, None)
