from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import InlineKeyboardMarkup, MessageEntity, Update
from sqlalchemy import select

from assistant.bot.keyboards import NoteCb, NoteItemCb
from assistant.bot.replies import NO_PREVIEW
from assistant.bot.routers import notes as notes_router
from assistant.bot.routers.notes import card_view, confirm_view, notes_view
from assistant.bot.texts import utf16_len
from assistant.core.i18n import translator
from assistant.core.models import Note
from assistant.core.services import notes
from assistant.core.services.notes import Item, NoteView
from tests.bot.fakes import callback_update, message_update

RU, EN = translator("ru"), translator("en")
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)  # when the test's notes were written
CLOCK = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # the bot's clock
SALE = "https://example.com/sale"
GONE = "Этого уже нет."
STALE = "Эта кнопка устарела — открой раздел заново из меню."
EMPTY = "📝 Заметок пока нет. Нажми «➕ Заметка» или «☑️ Список», чтобы создать первую."
TOOLS = ["➕ Заметка", "☑️ Список", "🔍 Найти"]  # under the notes of a list
MAX_ID = 2**63 - 1


@pytest.fixture(autouse=True)
def bot_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notes_router, "clock", lambda: CLOCK)


def press(action: str, note_id: int = 0, page: int = 0, *, user_id: int = 1) -> Update:
    return callback_update(NoteCb(action=action, id=note_id, page=page).pack(), user_id=user_id)


def tick(note_id: int, item_id: int, done: int, *, user_id: int = 1) -> Update:
    data = NoteItemCb(note=note_id, id=item_id, done=done).pack()
    return callback_update(data, user_id=user_id)


def shown(fake) -> EditMessageText:
    return fake.of(EditMessageText)[-1]


def last_answer(fake) -> AnswerCallbackQuery:
    return fake.of(AnswerCallbackQuery)[-1]


def buttons(markup: InlineKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


def data(markup: InlineKeyboardMarkup) -> list[list[str | None]]:
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def view(
    note_id: int,
    text: str,
    *,
    pinned: bool = False,
    items: Sequence[tuple[str, bool]] = (),
) -> NoteView:
    checklist = [Item(number, line, done) for number, (line, done) in enumerate(items, start=1)]
    return NoteView(note_id, text, NOW if pinned else None, NOW, NOW, checklist)


async def make_note(
    session, text: str, items: Sequence[str] = (), *, pinned: bool = False
) -> NoteView:
    note = await notes.create(session, 1, text, items, pinned=pinned, now=NOW)
    await session.commit()
    return note


async def checks(session, note_id: int) -> list[bool]:
    return [item.done for item in (await notes.get_view(session, 1, note_id)).items]


async def test_add_note_dialog(feed, fake, session) -> None:
    await feed(message_update("📝 Заметки"))
    empty = fake.of(SendMessage)[-1]
    assert empty.text == EMPTY
    assert buttons(empty.reply_markup) == [["➕ Заметка", "☑️ Список"]]  # nothing to search
    assert data(empty.reply_markup) == [
        [NoteCb(action="add").pack(), NoteCb(action="checklist").pack()]
    ]
    await feed(callback_update(NoteCb(action="add").pack()))
    assert fake.sent_texts()[-1] == "✍️ Напиши текст заметки (до 500 символов):"
    await feed(message_update("a" * 501))
    assert fake.sent_texts()[-1] == ("Заметка — это текст от 1 до 500 символов. Попробуй ещё раз:")
    await feed(message_update("  купить хлеб  "))
    assert fake.sent_texts()[-1] == "✅ Заметка сохранена."
    await feed(message_update("📝 Заметки"))
    listed = fake.of(SendMessage)[-1]
    assert listed.text == "📝 Твои заметки (1/50):\n\n1. купить хлеб"
    stored = (await session.scalars(select(Note))).all()
    assert [(n.text, n.created_at) for n in stored] == [("купить хлеб", CLOCK)]  # the bot's clock
    assert buttons(listed.reply_markup) == [["1. купить хлеб"], TOOLS]
    assert data(listed.reply_markup) == [
        [NoteCb(action="open", id=stored[0].id).pack()],
        [
            NoteCb(action="add").pack(),
            NoteCb(action="checklist").pack(),
            NoteCb(action="find").pack(),
        ],
    ]


async def test_note_of_exactly_500_characters_is_saved(feed, fake) -> None:
    await feed(callback_update(NoteCb(action="add").pack()))
    await feed(message_update("я" * 500))
    assert fake.sent_texts()[-1] == "✅ Заметка сохранена."


def hidden_link(offset: int, length: int) -> list[MessageEntity]:
    return [MessageEntity(type="text_link", offset=offset, length=length, url=SALE)]


async def test_a_new_note_keeps_its_hidden_link(feed, fake, session) -> None:
    await feed(callback_update(NoteCb(action="add").pack()))
    # Telegram counts in UTF-16: «🔥» is two units, so «тут» starts at 10.
    await feed(message_update("🔥 Скидки тут", entities=hidden_link(10, 3)))
    assert fake.sent_texts()[-1] == "✅ Заметка сохранена."
    stored = (await session.scalars(select(Note))).all()
    assert [n.text for n in stored] == [f"🔥 Скидки тут ({SALE})"]


async def test_a_new_note_is_measured_with_its_links_written_out(feed, fake, session) -> None:
    await feed(callback_update(NoteCb(action="add").pack()))
    # 500 characters as sent, past the limit with the address after «тут».
    await feed(message_update("я" * 497 + "тут", entities=hidden_link(497, 3)))
    assert fake.sent_texts()[-1] == "Заметка — это текст от 1 до 500 символов. Попробуй ещё раз:"
    assert await notes.count(session, 1) == 0


async def test_the_list_shows_the_pinned_on_top_then_the_newest(
    feed, fake, session, make_user
) -> None:
    await make_user()
    await make_note(session, "старая")
    shopping = await make_note(session, "Покупки", ["молоко", "хлеб", "сыр", "чай", "мёд"])
    for item in shopping.items[:2]:
        await notes.set_item(session, 1, shopping.id, item.id, True)
    await session.commit()
    password = await make_note(session, "Пароль от wifi: hunter2")
    await make_note(session, "новая")
    await notes.set_pinned(session, 1, password.id, True, NOW)
    await session.commit()
    await feed(message_update("📝 Заметки"))
    listed = fake.of(SendMessage)[-1]
    assert listed.text == (
        "📝 Твои заметки (4/50):\n"
        "\n"
        "1. 📌 Пароль от wifi: hunter2\n"
        "2. новая\n"
        "3. Покупки ✅ 2/5\n"
        "4. старая"
    )
    assert buttons(listed.reply_markup) == [
        ["1. 📌 Пароль от wifi: hunter2"],
        ["2. новая"],
        ["3. Покупки ✅ 2/5"],
        ["4. старая"],
        TOOLS,
    ]
    # The addresses a note keeps are not the message's point: no preview card under the list.
    assert listed.link_preview_options == NO_PREVIEW


def test_a_long_note_is_one_line_in_the_list_and_shorter_on_its_button() -> None:
    long = view(7, "Первая строка\n" + "я" * 200, pinned=True, items=[("молоко", True)])
    text, markup = notes_view([long], 0, RU)
    assert text.splitlines()[2] == "1. 📌 Первая строка " + "я" * 85 + "… ✅ 1/1"  # 100 characters
    assert buttons(markup) == [["1. 📌 Первая строка " + "я" * 15 + "… ✅ 1/1"], TOOLS]
    text, markup = notes_view([view(7, "Shopping", items=[("milk", False)])], 0, EN)
    assert text == "📝 Your notes (1/50):\n\n1. Shopping ✅ 0/1"
    assert buttons(markup) == [["1. Shopping ✅ 0/1"], ["➕ Note", "☑️ List", "🔍 Find"]]
    text, markup = notes_view([], 0, EN)
    assert text == "📝 No notes yet. Tap “➕ Note” or “☑️ List” to create the first one."
    assert buttons(markup) == [["➕ Note", "☑️ List"]]


async def test_fifty_long_notes_fit_telegram_limits(feed, fake, session, make_user) -> None:
    await make_user()
    for number in range(50):
        await notes.create(session, 1, f"{number:02d}" + "ж" * 498, now=NOW)
    await session.commit()
    await feed(message_update("📝 Заметки"))
    [first] = fake.of(SendMessage)
    assert first.text.splitlines()[2] == "1. 49" + "ж" * 97 + "…"  # the newest first
    assert first.text.endswith("Стр. 1 из 10")
    rows = first.reply_markup.inline_keyboard
    assert len(rows) == 7
    assert [b.text for b in rows[5]] == TOOLS and [b.text for b in rows[6]] == ["▶️"]
    assert all(len(b.callback_data.encode()) <= 64 for row in rows for b in row)
    await feed(press("page", page=9))
    last = shown(fake)
    assert "46. 04жж" in last.text and last.text.endswith("Стр. 10 из 10")
    assert [b.text for b in last.reply_markup.inline_keyboard[6]] == ["◀️"]
    await feed(callback_update(NoteCb(action="add").pack()))
    answer = last_answer(fake)
    assert answer.show_alert and answer.text == "Достигнут лимит — 50 заметок. Удали лишние."


def test_a_card_shows_the_text_whole_then_the_items() -> None:
    note = view(7, "Покупки\nв субботу", pinned=True, items=[("молоко", False), ("хлеб", True)])
    text, markup = card_view(note, 2, RU)
    assert text == "📌 Покупки\nв субботу\n\n⬜ молоко\n✅ хлеб"
    assert buttons(markup) == [
        ["⬜ молоко"],
        ["✅ хлеб"],
        ["➕ Пункты", "🧹 Убрать отмеченные"],
        ["📌 Открепить", "✏️ Изменить"],
        ["🗑 Удалить", "↩️ К заметкам"],
    ]
    assert data(markup) == [
        [NoteItemCb(note=7, id=1, done=1).pack()],  # the open item's button checks it
        [NoteItemCb(note=7, id=2, done=0).pack()],  # the checked one's unchecks it
        [NoteCb(action="items", id=7, page=2).pack(), NoteCb(action="clear", id=7, page=2).pack()],
        [NoteCb(action="unpin", id=7, page=2).pack(), NoteCb(action="edit", id=7, page=2).pack()],
        [NoteCb(action="delask", id=7, page=2).pack(), NoteCb(action="page", page=2).pack()],
    ]
    # Nothing checked, nothing to clear; a plain note can get items and so become a checklist.
    _, markup = card_view(view(8, "Дела", items=[("позвонить", False)]), 0, RU)
    assert buttons(markup) == [
        ["⬜ позвонить"],
        ["➕ Пункты"],
        ["📌 Закрепить", "✏️ Изменить"],
        ["🗑 Удалить", "↩️ К заметкам"],
    ]
    text, markup = card_view(view(9, "Wi-Fi: hunter2"), 0, EN)
    assert text == "Wi-Fi: hunter2"
    assert buttons(markup) == [["➕ Items"], ["📌 Pin", "✏️ Edit"], ["🗑 Delete", "↩️ To notes"]]
    _, markup = card_view(view(9, "Shopping", pinned=True, items=[("milk", True)]), 0, EN)
    assert buttons(markup)[1:3] == [["➕ Items", "🧹 Remove checked"], ["📌 Unpin", "✏️ Edit"]]


def test_an_items_line_and_button_keep_40_characters() -> None:
    text, markup = card_view(view(7, "Дела", items=[("я" * 100, False)]), 0, RU)
    assert text == "Дела\n\n⬜ " + "я" * 39 + "…"
    assert buttons(markup)[0] == ["⬜ " + "я" * 39 + "…"]


def test_the_fullest_card_fits_whole() -> None:
    # 500 emoji of text and 20 items of 100 emoji: every item's line keeps 39 emoji and «…».
    items = [("🎉" * 100, number % 2 == 0) for number in range(20)]
    pinned = view(MAX_ID, "🎉" * 500, pinned=True, items=items)
    text, markup = card_view(pinned, 9, RU)
    assert utf16_len(text) == 2644  # of the 3900 a message keeps to: a card is never cut
    assert utf16_len(card_view(replace(pinned, pinned_at=None), 9, RU)[0]) == 2641
    assert all(len(b.callback_data.encode()) <= 64 for row in markup.inline_keyboard for b in row)
    assert buttons(markup)[20] == ["🧹 Убрать отмеченные"]  # 20 items: no room for «➕ Пункты»
    longest = NoteItemCb(note=MAX_ID, id=MAX_ID, done=1).pack()
    assert longest == f"ni:{MAX_ID}:{MAX_ID}:1" and len(longest.encode()) == 44


async def test_a_note_opens_as_its_card_and_goes_back_to_the_list(
    feed, fake, session, make_user
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко", "хлеб"])
    await feed(press("open", note.id))
    card = shown(fake)
    assert card.text == "Покупки\n\n⬜ молоко\n⬜ хлеб"
    assert card.link_preview_options == NO_PREVIEW
    await feed(callback_update(data(card.reply_markup)[-1][1]))  # «↩️ К заметкам»
    assert shown(fake).text == "📝 Твои заметки (1/50):\n\n1. Покупки ✅ 0/2"
    assert shown(fake).link_preview_options == NO_PREVIEW


async def test_an_items_button_sets_the_state_it_shows(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко", "хлеб"])
    milk, bread = note.items
    await feed(tick(note.id, milk.id, 1))
    card = shown(fake)
    assert card.text == "Покупки\n\n✅ молоко\n⬜ хлеб"
    assert data(card.reply_markup)[0] == [NoteItemCb(note=note.id, id=milk.id, done=0).pack()]
    assert card.link_preview_options == NO_PREVIEW
    # The same button again, a double tap: the item stays checked.
    await feed(tick(note.id, milk.id, 1))
    assert await checks(session, note.id) == [True, False]
    # A card shown before «хлеб» was checked in the app: its «⬜ хлеб» never unchecks it ...
    await notes.set_item(session, 1, note.id, bread.id, True)
    await session.commit()
    await feed(tick(note.id, bread.id, 1))
    assert await checks(session, note.id) == [True, True]
    # ... and its «✅ молоко» unchecks.
    await feed(tick(note.id, milk.id, 0))
    assert await checks(session, note.id) == [False, True]
    assert shown(fake).text == "Покупки\n\n⬜ молоко\n✅ хлеб"
    # A check is not an edit of the note.
    assert (await notes.get_view(session, 1, note.id)).updated_at == NOW


async def test_an_item_or_its_note_deleted_meanwhile(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко", "хлеб"])
    milk, bread = note.items
    await notes.delete_item(session, 1, note.id, milk.id)  # in the app
    await session.commit()
    await feed(tick(note.id, milk.id, 1))
    assert last_answer(fake).text == GONE
    assert shown(fake).text == "Покупки\n\n⬜ хлеб"  # the note's fresh card
    await notes.delete(session, 1, note.id)
    await session.commit()
    await feed(tick(note.id, bread.id, 1))
    assert last_answer(fake).text == GONE
    assert shown(fake).text == EMPTY


async def test_an_expired_query_after_a_check_still_refreshes_the_card(
    feed, fake, session, make_user
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко"])
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(tick(note.id, note.items[0].id, 1))
    assert fake.sent_texts() == ["Покупки\n\n✅ молоко"]


async def test_pinning_puts_the_note_on_top_without_editing_it(
    feed, fake, session, make_user
) -> None:
    await make_user()
    first = await make_note(session, "первая")
    await make_note(session, "вторая")
    await feed(press("pin", first.id, page=0))
    card = shown(fake)
    assert card.text == "📌 первая"
    assert buttons(card.reply_markup) == [
        ["➕ Пункты"],
        ["📌 Открепить", "✏️ Изменить"],
        ["🗑 Удалить", "↩️ К заметкам"],
    ]
    assert card.link_preview_options == NO_PREVIEW
    pinned = await notes.get_view(session, 1, first.id)
    assert (pinned.pinned_at, pinned.updated_at) == (CLOCK, NOW)  # the bot's clock; not an edit
    await feed(press("page"))
    assert shown(fake).text == "📝 Твои заметки (2/50):\n\n1. 📌 первая\n2. вторая"
    await feed(press("unpin", first.id))
    assert shown(fake).text == "первая"
    assert buttons(shown(fake).reply_markup)[1] == ["📌 Закрепить", "✏️ Изменить"]
    assert (await notes.get_view(session, 1, first.id)).pinned_at is None


async def test_a_sixth_pin_is_refused_and_a_pinned_note_stays_as_it_is(
    feed, fake, session, make_user
) -> None:
    await make_user()
    for number in range(5):
        await make_note(session, f"закреплённая {number}", pinned=True)
    extra = await make_note(session, "шестая")
    await feed(press("pin", extra.id))
    answer = last_answer(fake)
    assert answer.show_alert
    assert answer.text == "Закрепить можно не больше 5 заметок — открепи одну"
    assert not fake.of(EditMessageText)
    assert (await notes.get_view(session, 1, extra.id)).pinned_at is None
    # An old card's «📌 Закрепить» of a note pinned since: the pin stays where it was.
    pinned = (await notes.list_for(session, 1))[0]
    await feed(press("pin", pinned.id))
    assert shown(fake).text == "📌 закреплённая 4"
    assert (await notes.get_view(session, 1, pinned.id)).pinned_at == NOW
    answer = last_answer(fake)
    assert answer.text is None and not answer.show_alert


async def test_an_expired_query_at_the_pin_limit_is_no_error(
    feed, fake, session, make_user
) -> None:
    # A tap that waited out a restart is too old for the alert: nothing more goes wrong.
    await make_user()
    for number in range(5):
        await make_note(session, f"закреплённая {number}", pinned=True)
    extra = await make_note(session, "шестая")
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(press("pin", extra.id))
    assert [answer.show_alert for answer in fake.of(AnswerCallbackQuery)] == [True]
    assert fake.sent_texts() == []  # no "something went wrong"
    assert (await notes.get_view(session, 1, extra.id)).pinned_at is None


async def test_clearing_removes_the_checked_items(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко", "хлеб", "сыр"])
    milk, _, cheese = note.items
    for item in (milk, cheese):
        await notes.set_item(session, 1, note.id, item.id, True)
    await session.commit()
    await feed(press("open", note.id))
    assert buttons(shown(fake).reply_markup)[3] == ["➕ Пункты", "🧹 Убрать отмеченные"]
    await feed(press("clear", note.id))
    card = shown(fake)
    assert card.text == "Покупки\n\n⬜ хлеб"
    assert buttons(card.reply_markup) == [
        ["⬜ хлеб"],
        ["➕ Пункты"],
        ["📌 Закрепить", "✏️ Изменить"],
        ["🗑 Удалить", "↩️ К заметкам"],
    ]


async def test_back_to_notes_leads_to_the_page_the_note_is_on_now(
    feed, fake, session, make_user
) -> None:
    await make_user()
    oldest = await make_note(session, "самая старая")
    for number in range(6):
        await make_note(session, f"заметка {number}")
    await feed(press("open", oldest.id))  # the seventh: on the second page
    assert data(shown(fake).reply_markup)[-1][1] == NoteCb(action="page", page=1).pack()
    await feed(press("pin", oldest.id, page=1))  # pinned, it is the first
    back = data(shown(fake).reply_markup)[-1][1]
    assert back == NoteCb(action="page", page=0).pack()
    await feed(callback_update(back))
    assert shown(fake).text.splitlines()[2] == "1. 📌 самая старая"


async def test_delete_asks_first_and_goes_back_to_the_card(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко"])
    await feed(press("open", note.id))
    await feed(callback_update(data(shown(fake).reply_markup)[-1][0]))  # «🗑 Удалить»
    question = shown(fake)
    assert question.text == "🗑 Удалить заметку «Покупки»?"
    assert buttons(question.reply_markup) == [["🗑 Да, удалить", "↩️ Назад"]]
    assert data(question.reply_markup) == [
        [NoteCb(action="delyes", id=note.id).pack(), NoteCb(action="open", id=note.id).pack()]
    ]
    assert question.link_preview_options == NO_PREVIEW
    assert await notes.count(session, 1) == 1
    await feed(press("open", note.id))  # «↩️ Назад»
    assert shown(fake).text == "Покупки\n\n⬜ молоко"
    await feed(press("delyes", note.id))
    assert last_answer(fake).text == "🗑 Удалено"
    assert shown(fake).text == EMPTY
    assert await notes.count(session, 1) == 0
    await feed(press("delyes", note.id))  # the second tap
    assert last_answer(fake).text == GONE
    assert shown(fake).text == EMPTY


def test_the_question_names_the_note_in_30_characters() -> None:
    text, markup = confirm_view(view(7, "я" * 40), 3, RU)
    assert text == "🗑 Удалить заметку «" + "я" * 29 + "…»?"
    assert data(markup) == [
        [NoteCb(action="delyes", id=7, page=3).pack(), NoteCb(action="open", id=7, page=3).pack()]
    ]
    text, markup = confirm_view(view(7, "Shopping"), 0, EN)
    assert text == "🗑 Delete the note “Shopping”?"
    assert buttons(markup) == [["🗑 Yes, delete", "↩️ Back"]]


async def test_after_a_delete_the_list_shows_the_notes_page_or_the_last_left(
    feed, fake, session, make_user
) -> None:
    await make_user()
    made = [await make_note(session, f"заметка {number}") for number in range(7)]
    # The list: 6, 5, 4, 3, 2 on the first page, 1 and 0 on the second.
    await feed(press("open", made[1].id))  # its card leads back to the second page
    await feed(callback_update(data(shown(fake).reply_markup)[-1][0]))  # «🗑 Удалить»
    # The question passes the card's page on to both of its answers.
    question = data(shown(fake).reply_markup)
    assert question == [
        [
            NoteCb(action="delyes", id=made[1].id, page=1).pack(),
            NoteCb(action="open", id=made[1].id, page=1).pack(),
        ]
    ]
    await feed(callback_update(question[0][0]))  # «🗑 Да, удалить»
    assert shown(fake).text == "📝 Твои заметки (6/50):\n\n6. заметка 0\n\nСтр. 2 из 2"
    await feed(press("delyes", made[0].id, page=1))  # alone on its page: the last page left
    assert shown(fake).text.splitlines()[2:] == [f"{n}. заметка {7 - n}" for n in range(1, 6)]


async def test_an_old_delete_button_asks_first(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "секрет")
    await feed(press("del", note.id))  # «🗑 1» of a list sent before 2.6
    assert shown(fake).text == "🗑 Удалить заметку «секрет»?"
    assert await notes.count(session, 1) == 1


@pytest.mark.parametrize(
    "action",
    ["open", "fopen", "pin", "unpin", "clear", "edit", "items", "delask", "del", "delyes"],
)
async def test_a_button_of_a_deleted_note_shows_the_list(
    action, feed, fake, session, make_user
) -> None:
    await make_user()
    for number in range(6):
        await make_note(session, f"заметка {number}")
    gone = await make_note(session, "удалённая")
    await notes.delete(session, 1, gone.id)
    await session.commit()
    await feed(press(action, gone.id, page=1))
    assert last_answer(fake).text == GONE
    assert shown(fake).text.endswith("Стр. 1 из 2")  # from the start
    assert shown(fake).link_preview_options == NO_PREVIEW


async def test_buttons_with_someone_elses_note_find_nothing(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "секрет", ["пункт"])
    item = note.items[0]
    for update in (
        press("open", note.id, user_id=2),
        tick(note.id, item.id, 1, user_id=2),
        press("pin", note.id, user_id=2),
        press("clear", note.id, user_id=2),
        press("edit", note.id, user_id=2),
        press("items", note.id, user_id=2),
        press("delask", note.id, user_id=2),
        press("delyes", note.id, user_id=2),
    ):
        await feed(update)
        assert last_answer(fake).text == GONE
        assert shown(fake).text == EMPTY
    kept = await notes.get_view(session, 1, note.id)
    assert (kept.pinned_at, kept.items[0].done) == (None, False)
    assert not fake.of(SendMessage)  # no dialog began for the other user


async def test_an_old_button_never_hits_a_newer_note(feed, fake, session, make_user) -> None:
    await make_user()
    first = await make_note(session, "первая")
    await feed(press("delyes", first.id))
    assert last_answer(fake).text == "🗑 Удалено"
    second = await make_note(session, "вторая")
    assert second.id != first.id  # ids of deleted notes are never reused
    await feed(press("delyes", first.id))
    assert last_answer(fake).text == GONE
    assert [n.text for n in await notes.list_for(session, 1)] == ["вторая"]


async def test_expired_query_after_delete_still_refreshes_the_list(
    feed, fake, session, make_user
) -> None:
    await make_user()
    note = await make_note(session, "секрет")
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(press("delyes", note.id))
    assert await notes.count(session, 1) == 0
    # The list is refreshed, and there is no "something went wrong".
    assert fake.sent_texts() == [EMPTY]


async def test_an_expired_query_still_asks_before_a_delete(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "секрет")
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(press("delask", note.id))
    # The question comes all the same, and there is no "something went wrong".
    assert fake.sent_texts() == [confirm_view(note, 0, RU)[0]]
    assert await notes.count(session, 1) == 1


async def test_a_forged_item_button_is_a_stale_button(feed, fake) -> None:
    for forged in ("ni:1:1:2", "ni:1:1:-1", "ni:1:-1:1", f"ni:{MAX_ID + 1}:1:0", "ni:1:1"):
        await feed(callback_update(forged))
        assert last_answer(fake).text == STALE
