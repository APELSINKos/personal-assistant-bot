from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from sqlalchemy import select

from assistant.bot.keyboards import NoteCb
from assistant.core.models import Note
from assistant.core.services import notes
from tests.bot.fakes import callback_update, message_update


async def test_add_note_dialog(feed, fake, session) -> None:
    await feed(message_update("📝 Заметки"))
    assert fake.sent_texts()[-1] == (
        "📝 Заметок пока нет. Нажми «➕ Добавить», чтобы создать первую."
    )
    await feed(callback_update(NoteCb(action="add").pack()))
    assert fake.sent_texts()[-1] == "✍️ Напиши текст заметки (до 500 символов):"
    await feed(message_update("a" * 501))
    assert fake.sent_texts()[-1] == ("Заметка — это текст от 1 до 500 символов. Попробуй ещё раз:")
    await feed(message_update("  купить хлеб  "))
    assert fake.sent_texts()[-1] == "✅ Заметка сохранена."
    await feed(message_update("📝 Заметки"))
    assert fake.sent_texts()[-1] == "📝 Твои заметки (1/50):\n\n1. купить хлеб"
    assert [n.text for n in (await session.scalars(select(Note))).all()] == ["купить хлеб"]


async def test_note_of_exactly_500_characters_is_saved(feed, fake) -> None:
    await feed(callback_update(NoteCb(action="add").pack()))
    await feed(message_update("я" * 500))
    assert fake.sent_texts()[-1] == "✅ Заметка сохранена."


async def test_fifty_long_notes_fit_telegram_limits(feed, fake, session, make_user) -> None:
    await make_user()
    for number in range(50):
        await notes.create(session, 1, f"{number:02d}" + "ж" * 498)
    await session.commit()
    await feed(message_update("📝 Заметки"))
    [first] = fake.of(SendMessage)
    assert len(first.text) <= 4096 and first.text.endswith("Стр. 1 из 10")
    rows = first.reply_markup.inline_keyboard
    assert len(rows) == 7 and [b.text for b in rows[5]] == ["▶️"]
    assert all(len(b.callback_data.encode()) <= 64 for row in rows for b in row)
    await feed(callback_update(NoteCb(action="page", page=9).pack()))
    last = fake.of(EditMessageText)[-1]
    assert "46. 45жж" in last.text and last.text.endswith("Стр. 10 из 10")
    assert [b.text for b in last.reply_markup.inline_keyboard[5]] == ["◀️"]
    await feed(callback_update(NoteCb(action="add").pack()))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and answer.text == "Достигнут лимит — 50 заметок. Удали лишние."


async def test_delete_double_tap_and_foreign_id(feed, fake, session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "секрет")
    await session.commit()
    data = NoteCb(action="del", id=note.id).pack()
    await feed(callback_update(data, user_id=2))  # someone else's id in the button
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert await notes.count(session, 1) == 1
    await feed(callback_update(data))
    assert fake.of(AnswerCallbackQuery)[-1].text == "🗑 Удалено"
    await feed(callback_update(data))  # the second tap on the same button
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert fake.of(EditMessageText)[-1].text.startswith("📝 Заметок пока нет")


async def test_old_delete_button_never_hits_a_newer_note(feed, fake, session, make_user) -> None:
    await make_user()
    first = await notes.create(session, 1, "первая")
    await session.commit()
    await feed(message_update("📝 Заметки"))
    old_delete = fake.of(SendMessage)[-1].reply_markup.inline_keyboard[0][0].callback_data
    await feed(callback_update(old_delete))
    assert fake.of(AnswerCallbackQuery)[-1].text == "🗑 Удалено"
    second = await notes.create(session, 1, "вторая")
    await session.commit()
    assert second.id != first.id  # ids of deleted notes are never reused
    await feed(callback_update(old_delete))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert [n.text for n in await notes.all_for(session, 1)] == ["вторая"]


async def test_expired_query_after_delete_still_refreshes_the_list(
    feed, fake, session, make_user
) -> None:
    await make_user()
    note = await notes.create(session, 1, "секрет")
    await session.commit()
    fake.errors.append(
        TelegramBadRequest(
            method=AnswerCallbackQuery(callback_query_id="1"),
            message="Bad Request: query is too old and response timeout expired",
        )
    )
    await feed(callback_update(NoteCb(action="del", id=note.id).pack()))
    assert await notes.count(session, 1) == 0
    # The list is refreshed, and there is no "something went wrong".
    assert fake.sent_texts() == ["📝 Заметок пока нет. Нажми «➕ Добавить», чтобы создать первую."]
