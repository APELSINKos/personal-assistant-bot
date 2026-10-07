from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import InlineKeyboardMarkup, MessageEntity, Update

from assistant.bot.keyboards import NoteCb, NoteItemCb, cancel_menu, main_menu
from assistant.bot.replies import NO_PREVIEW
from assistant.bot.routers import notes as notes_router
from assistant.bot.routers.notes import card_view, results_view, split_list
from assistant.bot.texts import TEXT_LIMIT, utf16_len
from assistant.core.i18n import translator
from assistant.core.services import notes
from assistant.core.services.notes import Item, NoteView
from tests.bot.fakes import callback_update, message_update

RU, EN = translator("ru"), translator("en")
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)  # when the test's notes were written
CLOCK = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # the bot's clock
SALE = "https://example.com/sale"
GONE = "Этого уже нет."
MENU, CANCEL = main_menu(RU), cancel_menu(RU)
BAD_TEXT = "Заметка — это текст от 1 до 500 символов. Попробуй ещё раз:"
LIMIT = "Достигнут лимит — 50 заметок. Удали лишние."


@pytest.fixture(autouse=True)
def bot_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notes_router, "clock", lambda: CLOCK)


def press(action: str, note_id: int = 0, page: int = 0, *, message_id: int | None = None) -> Update:
    data = NoteCb(action=action, id=note_id, page=page).pack()
    return callback_update(data, message_id=message_id)


def sent(fake) -> list[SendMessage]:
    return fake.of(SendMessage)


def shown(fake) -> EditMessageText:
    return fake.of(EditMessageText)[-1]


def last_answer(fake) -> AnswerCallbackQuery:
    return fake.of(AnswerCallbackQuery)[-1]


def buttons(markup: InlineKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


def data(markup: InlineKeyboardMarkup) -> list[list[str | None]]:
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def hidden_link(text: str, words: str) -> list[MessageEntity]:
    # Every character of these texts is one UTF-16 unit, so a Python index is Telegram's offset.
    offset = text.index(words)
    return [MessageEntity(type="text_link", offset=offset, length=len(words), url=SALE)]


async def make_note(
    session, text: str, items: Sequence[str] = (), *, pinned: bool = False
) -> NoteView:
    note = await notes.create(session, 1, text, items, pinned=pinned, now=NOW)
    await session.commit()
    return note


async def dialog(dp, bot) -> tuple[str | None, dict[str, Any]]:
    key = StorageKey(bot_id=bot.id, chat_id=1, user_id=1)
    return await dp.storage.get_state(key), await dp.storage.get_data(key)


async def search_for(feed, fake, dp, bot, words: str) -> int:
    """Search the notes as the user does; the id Telegram gave the message with the results."""
    await feed(callback_update(NoteCb(action="find").pack()))
    await feed(message_update(words))
    results = fake.messages[-1]
    assert results.text.startswith("🔍 «")  # not «🔍 Нашлось», the message before it
    # The search applies itself in that message alone, so it keeps that message's id.
    assert (await dialog(dp, bot))[1]["notes_query_message"] == results.message_id
    return results.message_id


async def test_an_edit_replaces_the_text_and_keeps_the_items(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко"])
    await feed(press("edit", note.id))
    ask = sent(fake)[-1]
    assert (ask.text, ask.reply_markup) == (
        "✍️ Напиши новый текст заметки (до 500 символов):",
        CANCEL,
    )
    assert await dialog(dp, bot) == (
        "NoteForm:edit",
        {"hint": "hint-note-edit", "note_id": note.id},
    )
    await feed(message_update("я" * 501))
    assert fake.sent_texts()[-1] == BAD_TEXT
    assert (await dialog(dp, bot))[0] == "NoteForm:edit"  # the dialog waits
    text = "Скидки тут\nв субботу"
    await feed(message_update(text, entities=hidden_link(text, "тут")))
    done, card = sent(fake)[-2:]
    # One message cannot carry both the main menu and the card's buttons: two of them.
    assert (done.text, done.reply_markup) == ("✅ Заметка изменена.", MENU)
    assert card.text == f"Скидки тут ({SALE})\nв субботу\n\n⬜ молоко"
    assert card.link_preview_options == NO_PREVIEW
    assert data(card.reply_markup)[-1] == [
        NoteCb(action="delask", id=note.id).pack(),
        NoteCb(action="page").pack(),
    ]
    assert await dialog(dp, bot) == (None, {})


async def test_an_edit_is_measured_with_its_links_written_out(
    feed, fake, session, make_user
) -> None:
    await make_user()
    note = await make_note(session, "Покупки")
    await feed(press("edit", note.id))
    text = "я" * 497 + "тут"  # 500 characters as sent, past the limit with the address
    await feed(message_update(text, entities=hidden_link(text, "тут")))
    assert fake.sent_texts()[-1] == BAD_TEXT
    assert (await notes.get_view(session, 1, note.id)).text == "Покупки"


@pytest.mark.parametrize(("action", "reply"), [("edit", "новый текст"), ("items", "хлеб")])
async def test_a_note_deleted_during_its_dialog_ends_it(
    action, reply, feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко"])
    await feed(press(action, note.id))
    await notes.delete(session, 1, note.id)  # in the app
    await session.commit()
    await feed(message_update(reply))
    last = sent(fake)[-1]
    assert (last.text, last.reply_markup) == (GONE, MENU)
    assert await dialog(dp, bot) == (None, {})


async def test_items_come_a_line_each_without_their_markers(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", ["молоко"])
    await feed(press("items", note.id))
    ask = sent(fake)[-1]
    assert (ask.text, ask.reply_markup) == (
        "✍️ Напиши пункты — каждый с новой строки (в заметке до 20):",
        CANCEL,
    )
    assert await dialog(dp, bot) == ("NoteForm:items", {"hint": "hint-items", "note_id": note.id})
    # A ballot box from the emoji keyboard comes with U+FE0F; «[x]» and «☑» only go: a new item
    # is open. «1.5 кг» is no marker.
    text = "- [ ] хлеб\n1. [x] сыр\n\n☑️ чай тут\n1.5 кг яблок"
    await feed(message_update(text, entities=hidden_link(text, "тут")))
    done, card = sent(fake)[-2:]
    assert (done.text, done.reply_markup) == ("✅ Добавлено пунктов: 4", MENU)
    assert card.text == (
        f"Покупки\n\n⬜ молоко\n⬜ хлеб\n⬜ сыр\n⬜ чай тут ({SALE})\n⬜ 1.5 кг яблок"
    )
    assert card.link_preview_options == NO_PREVIEW
    assert await dialog(dp, bot) == (None, {})
    # Items are no edit of the note.
    assert (await notes.get_view(session, 1, note.id)).updated_at == NOW


async def test_items_that_do_not_fit_are_refused_whole(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", [f"пункт {number}" for number in range(17)])
    await feed(press("items", note.id))
    await feed(message_update("хлеб\nКупить в магазине у дома " + "я" * 100))
    refusal = sent(fake)[-1]
    assert refusal.text == (
        "Пункт «Купить в магазине у…» длиннее 100 символов — сократи и напиши ещё раз:"
    )
    assert refusal.link_preview_options == NO_PREVIEW  # it may quote an address
    await feed(message_update("хлеб\nсыр\nчай\nмёд"))
    assert fake.sent_texts()[-1] == "В заметку поместится ещё 3 пункта — напиши меньше:"
    await feed(message_update("- [ ]"))  # markers alone: no item
    assert fake.sent_texts()[-1] == "Напиши пункты, каждый с новой строки."
    assert (await notes.get_view(session, 1, note.id)).total == 17  # nothing kept so far
    assert (await dialog(dp, bot))[0] == "NoteForm:items"
    await feed(message_update("хлеб\nсыр\nчай"))
    done, card = sent(fake)[-2:]
    assert done.text == "✅ Добавлено пунктов: 3"
    assert "➕ Пункты" not in sum(buttons(card.reply_markup), [])  # 20 now: no room for more


async def test_a_note_filled_up_in_the_app_during_the_dialog(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    note = await make_note(session, "Покупки", [f"пункт {number}" for number in range(19)])
    await feed(press("items", note.id))
    await notes.add_items(session, 1, note.id, ["из приложения"])
    await session.commit()
    await feed(message_update("хлеб"))
    full, card = sent(fake)[-2:]
    assert (full.text, full.reply_markup) == ("В заметке уже 20 пунктов", MENU)
    assert card.text.endswith("⬜ пункт 18\n⬜ из приложения")
    assert await dialog(dp, bot) == (None, {})
    # The «➕ Пункты» of a card shown before says the same and starts nothing.
    await feed(press("items", note.id))
    answer = last_answer(fake)
    assert answer.show_alert and answer.text == "В заметке уже 20 пунктов"
    assert await dialog(dp, bot) == (None, {})


async def test_a_checklist_is_a_title_and_its_items(feed, fake, session, dp, bot) -> None:
    await feed(callback_update(NoteCb(action="checklist").pack()))
    ask = sent(fake)[-1]
    assert ask.text == (
        "☑️ Напиши список: в первой строке — название, дальше каждый пункт с новой строки. "
        "Например:\nПокупки\nмолоко\nхлеб"
    )
    assert ask.reply_markup == CANCEL
    assert await dialog(dp, bot) == ("NoteForm:checklist", {"hint": "hint-list"})
    await feed(message_update("Покупки"))
    assert fake.sent_texts()[-1] == (
        "Нужен хотя бы один пункт — каждый с новой строки после названия."
    )
    # The title keeps a marker it starts with; hidden links are written out everywhere.
    text = "- Покупки тут\n- молоко\n• хлеб"
    await feed(message_update(text, entities=hidden_link(text, "тут")))
    done, card = sent(fake)[-2:]
    assert (done.text, done.reply_markup) == ("✅ Список сохранён.", MENU)
    assert card.text == f"- Покупки тут ({SALE})\n\n⬜ молоко\n⬜ хлеб"
    assert card.link_preview_options == NO_PREVIEW
    [stored] = await notes.list_for(session, 1)
    assert (stored.created_at, stored.updated_at) == (CLOCK, CLOCK)  # the bot's clock
    assert await dialog(dp, bot) == (None, {})


async def test_a_checklist_is_refused_whole(feed, fake, session) -> None:
    await feed(callback_update(NoteCb(action="checklist").pack()))
    items = [f"пункт {number}" for number in range(21)]
    await feed(message_update("\n".join(["Покупки", *items])))
    assert fake.sent_texts()[-1] == "В списке может быть до 20 пунктов — напиши короче:"
    title = "я" * 497 + "тут"  # 500 characters as sent, past the limit with the address
    text = f"{title}\nмолоко"
    await feed(message_update(text, entities=hidden_link(text, "тут")))
    assert fake.sent_texts()[-1] == BAD_TEXT
    item = "https://example.com/" + "ж" * 81  # 101 characters
    await feed(message_update(f"Покупки\nмолоко\n{item}"))
    refusal = sent(fake)[-1]
    assert refusal.text == (
        "Пункт «https://example.com/…» длиннее 100 символов — сократи и напиши ещё раз:"
    )
    assert refusal.link_preview_options == NO_PREVIEW  # no card for the address it quotes
    assert await notes.count(session, 1) == 0
    await feed(message_update("\n".join(["я" * 500, *items[:20]])))  # both limits, exactly
    assert sent(fake)[-2].text == "✅ Список сохранён."
    [stored] = await notes.list_for(session, 1)
    assert (len(stored.text), stored.total) == (500, 20)


async def test_an_item_of_exactly_100_characters_is_kept(feed, fake, session, make_user) -> None:
    await make_user()
    note = await make_note(session, "Покупки")
    await feed(press("items", note.id))
    await feed(message_update("ж" * 100))
    assert sent(fake)[-2].text == "✅ Добавлено пунктов: 1"
    await feed(press("checklist"))
    await feed(message_update("Дела\n" + "з" * 100))
    assert sent(fake)[-2].text == "✅ Список сохранён."
    kept = [item.text for listed in await notes.list_for(session, 1) for item in listed.items]
    assert kept == ["з" * 100, "ж" * 100]  # the newest note first


async def test_a_checklist_at_the_limit_of_notes(feed, fake, session, make_user, dp, bot) -> None:
    await make_user()
    for number in range(49):
        await notes.create(session, 1, f"заметка {number}", now=NOW)
    await session.commit()
    await feed(callback_update(NoteCb(action="checklist").pack()))
    assert (await dialog(dp, bot))[0] == "NoteForm:checklist"
    await notes.create(session, 1, "из приложения", now=NOW)  # the 50th, while the question is open
    await session.commit()
    await feed(message_update("Покупки\nмолоко"))
    last = sent(fake)[-1]
    assert (last.text, last.reply_markup) == (LIMIT, MENU)
    assert await dialog(dp, bot) == (None, {})
    await feed(callback_update(NoteCb(action="checklist").pack()))
    answer = last_answer(fake)
    assert answer.show_alert and answer.text == LIMIT
    assert await dialog(dp, bot) == (None, {})


@pytest.mark.parametrize(
    ("action", "hint"),
    [
        ("edit", "Напиши новый текст заметки."),
        ("items", "Напиши пункты, каждый с новой строки."),
        ("checklist", "Напиши название и пункты, каждый с новой строки."),
        ("find", "Напиши слово для поиска."),
    ],
)
async def test_a_dialog_asks_for_text_with_its_hint(
    action, hint, feed, fake, session, make_user
) -> None:
    await make_user()
    note = await make_note(session, "Покупки")
    await feed(press(action, note.id))
    await feed(message_update(sticker=True))
    assert fake.sent_texts()[-1] == f"Нужен текст. {hint}"


async def test_a_search_finds_every_word_in_any_case_and_in_the_items(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    password = await make_note(session, "Пароль от WiFi: hunter2")
    await make_note(session, "Елка на Новый год")
    await make_note(session, "Покупки", ["молоко", "хлеб"])
    await feed(callback_update(NoteCb(action="find").pack()))
    ask = sent(fake)[-1]
    assert (ask.text, ask.reply_markup) == ("🔍 Что найти? Напиши слово или часть слова:", CANCEL)
    assert await dialog(dp, bot) == ("NoteForm:search", {"hint": "hint-search"})
    await feed(message_update("wifi"))
    found, results = sent(fake)[-2:]
    assert (found.text, found.reply_markup) == ("🔍 Нашлось: 1 заметка", MENU)
    assert results.text == "🔍 «wifi» — 1 заметка:\n\n1. Пароль от WiFi: hunter2"
    assert buttons(results.reply_markup) == [["1. Пароль от WiFi: hunter2"], ["✖️ Сбросить поиск"]]
    assert data(results.reply_markup) == [
        [NoteCb(action="fopen", id=password.id).pack()],
        [NoteCb(action="reset").pack()],
    ]
    assert results.link_preview_options == NO_PREVIEW
    # The dialog is over; the search stays with the message of its results, by the id Telegram
    # gave that message, not the one before it.
    given = fake.messages[-1]
    assert given.text == results.text
    assert await dialog(dp, bot) == (
        None,
        {"hint": "hint-search", "notes_query": "wifi", "notes_query_message": given.message_id},
    )
    for words, first in (("ёлка", "1. Елка на Новый год"), ("хлеб  МОЛОКО", "1. Покупки ✅ 0/2")):
        await search_for(feed, fake, dp, bot, words)
        assert sent(fake)[-1].text.splitlines()[2] == first


async def test_a_search_that_finds_nothing_waits_for_other_words(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    await make_note(session, "Пароль от WiFi")
    await feed(callback_update(NoteCb(action="find").pack()))
    await feed(message_update("пароль   от\nпочты"))
    nothing = sent(fake)[-1]
    assert nothing.text == "🔍 По запросу «пароль от почты» ничего не нашлось. Напиши по-другому:"
    assert nothing.link_preview_options == NO_PREVIEW  # the words quoted may be an address
    await feed(message_update("я" * 51))
    assert fake.sent_texts()[-1] == "Запрос — до 50 символов. Напиши короче:"
    assert await dialog(dp, bot) == ("NoteForm:search", {"hint": "hint-search"})
    await feed(message_update("пароль"))
    assert sent(fake)[-2].text == "🔍 Нашлось: 1 заметка"


async def test_results_and_their_cards_apply_the_search_only_in_their_message(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    coffee = [await make_note(session, f"кофе {number}") for number in range(7)]
    for number in range(5):
        await make_note(session, f"чай {number}")
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    results = sent(fake)[-1]
    assert results.text == (
        "🔍 «кофе» — 7 заметок:\n\n"
        "1. кофе 6\n2. кофе 5\n3. кофе 4\n4. кофе 3\n5. кофе 2\n\nСтр. 1 из 2"
    )
    assert buttons(results.reply_markup)[5:] == [["▶️"], ["✖️ Сбросить поиск"]]
    assert data(results.reply_markup)[5] == [NoteCb(action="fpage", page=1).pack()]
    second = "🔍 «кофе» — 7 заметок:\n\n6. кофе 1\n7. кофе 0\n\nСтр. 2 из 2"
    await feed(press("fpage", page=1, message_id=message_id))
    assert shown(fake).text == second
    assert shown(fake).link_preview_options == NO_PREVIEW
    assert data(shown(fake).reply_markup)[1] == [
        NoteCb(action="fopen", id=coffee[0].id, page=1).pack()
    ]
    # The oldest coffee: on the second page of the results, on the third of the whole list.
    await feed(press("fopen", coffee[0].id, page=1, message_id=message_id))
    card = shown(fake)
    assert card.text == "кофе 0"
    back = NoteCb(action="fpage", page=1).pack()
    assert data(card.reply_markup)[-1][1] == back
    await feed(callback_update(back, message_id=message_id))  # «↩️ К заметкам»
    assert shown(fake).text == second
    # The same buttons in any other message work as the list's, with nothing said.
    await feed(press("fpage", page=1))
    assert shown(fake).text.splitlines()[2] == "6. кофе 6"
    assert shown(fake).text.endswith("Стр. 2 из 3")
    answer = last_answer(fake)
    assert answer.text is None and not answer.show_alert
    await feed(press("fopen", coffee[0].id, page=1))
    assert data(shown(fake).reply_markup)[-1][1] == NoteCb(action="page", page=2).pack()
    # The list's own buttons never apply the search, in its message too.
    await feed(press("page", page=1, message_id=message_id))
    assert shown(fake).text.startswith("📝 Твои заметки (12/50):")


async def test_a_tick_and_the_delete_question_keep_the_way_back_to_the_results(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    shopping = await make_note(session, "Покупки", ["молоко"])
    await make_note(session, "Пароль")
    message_id = await search_for(feed, fake, dp, bot, "покупки")
    to_results = NoteCb(action="fpage").pack()
    tick = NoteItemCb(note=shopping.id, id=shopping.items[0].id, done=1).pack()
    await feed(callback_update(tick, message_id=message_id))
    card = shown(fake)
    assert card.text == "Покупки\n\n✅ молоко"
    assert data(card.reply_markup)[-1][1] == to_results
    await feed(press("delask", shopping.id, message_id=message_id))
    no = NoteCb(action="open", id=shopping.id).pack()  # «↩️ Назад»
    assert data(shown(fake).reply_markup)[0][1] == no
    await feed(callback_update(no, message_id=message_id))
    assert shown(fake).text == "Покупки\n\n✅ молоко"
    assert data(shown(fake).reply_markup)[-1][1] == to_results


async def test_a_delete_goes_back_to_the_results_until_nothing_is_found(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    milk = await make_note(session, "кофе с молоком")
    sugar = await make_note(session, "кофе без сахара")
    tea = await make_note(session, "чай")
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    await feed(press("delyes", sugar.id, message_id=message_id))
    assert last_answer(fake).text == "🗑 Удалено"
    assert shown(fake).text == "🔍 «кофе» — 1 заметка:\n\n1. кофе с молоком"
    await feed(press("delyes", milk.id, message_id=message_id))
    # Nothing left to find: the whole list from its start, and the search is over.
    assert shown(fake).text == "📝 Твои заметки (1/50):\n\n1. чай"
    assert "notes_query" not in (await dialog(dp, bot))[1]
    await feed(press("open", tea.id, message_id=message_id))
    assert data(shown(fake).reply_markup)[-1][1] == NoteCb(action="page").pack()


@pytest.mark.parametrize(("delete", "count"), [(False, 12), (True, 11)], ids=["turn", "delete"])
async def test_a_search_that_finds_nothing_any_more_shows_the_list_from_its_start(
    delete, count, feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    coffee = [await make_note(session, f"кофе {number}") for number in range(7)]
    for number in range(5):
        await make_note(session, f"чай {number}")
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    # In the app no note is coffee any more, or only the oldest, on the second page of the
    # results, which is then deleted here.
    for note in coffee[1:] if delete else coffee:
        await notes.update_text(session, 1, note.id, "сок")
    await session.commit()
    if delete:
        await feed(press("delyes", coffee[0].id, page=1, message_id=message_id))
    else:  # «▶️» of the first page
        await feed(press("fpage", page=1, message_id=message_id))
    # The search is over: the whole list from its first page, not the page of the button.
    assert shown(fake).text == (
        f"📝 Твои заметки ({count}/50):\n\n"
        "1. чай 4\n2. чай 3\n3. чай 2\n4. чай 1\n5. чай 0\n\nСтр. 1 из 3"
    )
    assert "notes_query" not in (await dialog(dp, bot))[1]


async def test_a_deleted_note_of_the_results_shows_them_from_the_start(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    coffee = [await make_note(session, f"кофе {number}") for number in range(7)]
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    await notes.delete(session, 1, coffee[0].id)  # in the app
    await session.commit()
    await feed(press("pin", coffee[0].id, page=1, message_id=message_id))
    assert last_answer(fake).text == GONE
    assert shown(fake).text.startswith("🔍 «кофе» — 6 заметок:\n\n1. кофе 6\n")


async def test_a_note_the_search_finds_no_more_keeps_the_page_of_its_button(
    feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    coffee = [await make_note(session, f"кофе {number}") for number in range(7)]
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    await notes.update_text(session, 1, coffee[0].id, "чай")  # in the app
    await session.commit()
    await feed(press("fopen", coffee[0].id, page=9, message_id=message_id))
    card = shown(fake)
    assert card.text == "чай"
    # Six notes found now, two pages: the button's page as far as there are pages.
    assert data(card.reply_markup)[-1][1] == NoteCb(action="fpage", page=1).pack()


async def test_reset_brings_the_whole_list_back(feed, fake, session, make_user, dp, bot) -> None:
    await make_user()
    coffee = await make_note(session, "кофе")
    await make_note(session, "чай")
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    # «✖️ Сбросить поиск» of an older message leaves the search of this one.
    await feed(press("reset"))
    assert shown(fake).text == "📝 Твои заметки (2/50):\n\n1. чай\n2. кофе"
    assert (await dialog(dp, bot))[1]["notes_query"] == "кофе"
    await feed(press("reset", message_id=message_id))
    listed = shown(fake)
    assert listed.text == "📝 Твои заметки (2/50):\n\n1. чай\n2. кофе"
    assert listed.link_preview_options == NO_PREVIEW
    kept = (await dialog(dp, bot))[1]
    assert "notes_query" not in kept and "notes_query_message" not in kept
    # The results' buttons work as the list's now.
    await feed(press("fopen", coffee.id, message_id=message_id))
    assert data(shown(fake).reply_markup)[-1][1] == NoteCb(action="page").pack()


@pytest.mark.parametrize(
    "drop",
    [
        lambda: message_update("📝 Заметки"),
        lambda: message_update("/start"),
        lambda: message_update("/cancel"),
        lambda: callback_update(NoteCb(action="add").pack()),
    ],
    ids=["menu", "start", "cancel", "another-dialog"],
)
async def test_the_menu_commands_and_another_dialog_drop_the_search(
    drop, feed, fake, session, make_user, dp, bot
) -> None:
    await make_user()
    await make_note(session, "кофе")
    await make_note(session, "чай")
    message_id = await search_for(feed, fake, dp, bot, "кофе")
    await feed(drop())
    assert "notes_query" not in (await dialog(dp, bot))[1]
    await feed(press("fpage", message_id=message_id))
    assert shown(fake).text == "📝 Твои заметки (2/50):\n\n1. чай\n2. кофе"
    assert last_answer(fake).text is None


def test_a_list_message_is_its_title_and_then_its_items() -> None:
    assert split_list("Покупки\n- молоко\n\n• хлеб") == ("Покупки", ["молоко", "хлеб"])
    # The first line with words is the title, its marker kept.
    assert split_list(" \n- [ ] Дела \n1) позвонить\n2) [x] написать") == (
        "- [ ] Дела",
        ["позвонить", "написать"],
    )
    assert split_list("Покупки") == ("Покупки", [])
    assert split_list(" \n ") == ("", [])


def test_results_name_the_search_and_fit_telegram() -> None:
    checklist = [Item(number, "🎉" * 100, True) for number in range(1, 21)]
    found = [NoteView(n, "🎉" * 500, NOW, NOW, NOW, checklist) for n in range(1, 51)]
    text, markup = results_view(found, "🎉" * 50, 9, RU)
    assert text.splitlines()[0] == "🔍 «" + "🎉" * 50 + "» — 50 заметок:"
    assert text.endswith("Стр. 10 из 10")
    assert utf16_len(text) <= TEXT_LIMIT
    assert all(len(b.callback_data.encode()) <= 64 for row in markup.inline_keyboard for b in row)
    text, markup = results_view([NoteView(7, "Wi-Fi: hunter2", None, NOW, NOW)], "wifi", 0, EN)
    assert text == "🔍 “wifi” — 1 note:\n\n1. Wi-Fi: hunter2"
    assert buttons(markup) == [["1. Wi-Fi: hunter2"], ["✖️ Clear search"]]


def test_a_card_in_the_results_leads_back_to_them() -> None:
    note = NoteView(7, "Wi-Fi", None, NOW, NOW)
    _, markup = card_view(note, 3, RU, results=True)
    assert data(markup)[-1] == [
        NoteCb(action="delask", id=7, page=3).pack(),
        NoteCb(action="fpage", page=3).pack(),
    ]


@pytest.mark.parametrize(
    ("count", "ru", "en"),
    [
        (1, "1 пункт", "1 more item"),
        (3, "3 пункта", "3 more items"),
        (5, "5 пунктов", "5 more items"),
    ],
)
def test_the_room_left_for_items_in_words(count: int, ru: str, en: str) -> None:
    assert RU("items-room", count=count) == f"В заметку поместится ещё {ru} — напиши меньше:"
    assert EN("items-room", count=count) == f"Only {en} will fit — send fewer:"
