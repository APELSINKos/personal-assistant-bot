from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.methods import AnswerCallbackQuery, SendMessage
from sqlalchemy import select

from assistant.bot.keyboards import ReminderCb
from assistant.bot.routers import reminders as reminders_router
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import reminders
from tests.bot.fakes import callback_update, message_update

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # Monday, 15:00 in Moscow
ASK_TIME = "🕘 Во сколько? Выбери или напиши, например 18:30 или «завтра в 10»."


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW)


async def all_reminders(session) -> list[Reminder]:
    session.expire_all()
    return list((await session.scalars(select(Reminder).order_by(Reminder.id))).all())


def last_markup_texts(fake) -> list[str]:
    markup = fake.of(SendMessage)[-1].reply_markup
    return [button.text for row in markup.inline_keyboard for button in row]


async def test_a_phrase_anywhere_shows_a_card_and_creates(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    assert fake.sent_texts()[-1] == "⏰ Завтра, 09:00 — купить молоко"
    assert last_markup_texts(fake) == ["✅ Создать", "🕘 Другое время", "✖️ Отмена"]
    assert await all_reminders(session) == []
    await feed(callback_update(ReminderCb(action="ok").pack()))
    assert fake.sent_texts()[-1] == "✅ Напомню 29 сентября в 09:00: купить молоко"
    (stored,) = await all_reminders(session)
    assert stored.due_at == datetime(2026, 9, 29, 6, 0, tzinfo=UTC)


async def test_casual_message_never_creates_without_a_press(feed, fake, session) -> None:
    await feed(message_update("завтра экзамен, волнуюсь"))
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("привет"))  # not a time: ask again
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("/cancel"))
    assert await all_reminders(session) == []


async def test_missing_time_from_a_button(feed, fake, session) -> None:
    await feed(message_update("завтра позвонить маме"))
    assert fake.sent_texts()[-1] == ASK_TIME
    assert last_markup_texts(fake) == ["09:00", "12:00", "18:00"]
    await feed(callback_update(ReminderCb(action="t", value="18:00").pack()))
    assert fake.sent_texts()[-1] == "⏰ Завтра, 18:00 — позвонить маме"
    await feed(callback_update(ReminderCb(action="ok").pack()))
    (stored,) = await all_reminders(session)
    assert stored.due_at == datetime(2026, 9, 29, 15, 0, tzinfo=UTC)


async def test_a_repeat_card_and_the_list(feed, fake, session) -> None:
    await feed(message_update("по будням в 7:30 зарядка"))
    assert fake.sent_texts()[-1] == "↻ по будням в 07:30 — зарядка\nПервый раз: Завтра, 07:30"
    await feed(callback_update(ReminderCb(action="ok").pack()))
    assert fake.sent_texts()[-1] == "✅ Буду напоминать по будням в 07:30: зарядка"
    (stored,) = await all_reminders(session)
    assert stored.repeat is Repeat.WEEKLY and stored.weekdays == 31
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Твои напоминания (1/20):\n\n1. ↻ по будням в 07:30 — зарядка"
    )


async def test_another_time_and_cancel(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    await feed(callback_update(ReminderCb(action="retime").pack()))
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("послезавтра в 10"))
    assert fake.sent_texts()[-1] == "⏰ Послезавтра, 10:00 — купить молоко"
    await feed(callback_update(ReminderCb(action="no").pack()))
    assert fake.sent_texts()[-1] == "Отменено."
    assert await all_reminders(session) == []
    await feed(callback_update(ReminderCb(action="ok").pack()))  # the card is gone
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert await all_reminders(session) == []


async def test_a_past_time_asks_again(feed, fake) -> None:
    await feed(message_update("сегодня в 10 кино"))
    assert fake.sent_texts()[-2:] == ["Это время уже прошло. Укажи момент в будущем:", ASK_TIME]


async def test_the_add_button_asks_for_a_phrase(feed, fake) -> None:
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Активных напоминаний нет. Нажми «➕ Добавить», чтобы создать."
    )
    await feed(callback_update(ReminderCb(action="add").pack()))
    assert fake.sent_texts()[-1].startswith("✍️ Напиши, о чём и когда напомнить.")
    await feed(message_update("купить хлеб"))
    assert fake.sent_texts()[-1].startswith("🤔 Не нашёл, когда напомнить.")
    await feed(message_update("через 20 минут чай"))
    assert fake.sent_texts()[-1] == "⏰ Сегодня, 15:20 — чай"


async def test_a_phrase_without_text_asks_what(feed, fake) -> None:
    await feed(message_update("завтра в 9"))
    assert fake.sent_texts()[-1].startswith("✍️ О чём напомнить?")


async def test_deleting_a_repeat_asks_first(feed, fake, session, make_user) -> None:
    await feed(message_update("каждый день в 21 таблетки"))
    await feed(callback_update(ReminderCb(action="ok").pack()))
    (series,) = await all_reminders(session)
    await feed(callback_update(ReminderCb(action="delask", id=series.id).pack()))
    assert fake.sent_texts()[-1] == "Удалить повтор «таблетки» целиком?"
    await feed(callback_update(ReminderCb(action="del", id=series.id).pack()))
    (series,) = await all_reminders(session)
    assert series.status is ReminderStatus.CANCELLED


async def test_cancel_by_button_double_tap_and_foreign(feed, fake, session, make_user) -> None:
    user = await make_user()
    reminder = await reminders.create(session, user, "созвон", datetime(2099, 1, 1, 10, 0))
    await session.commit()
    data = ReminderCb(action="del", id=reminder.id).pack()
    await feed(callback_update(data, user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(callback_update(data))
    await feed(callback_update(data))
    assert [a.text for a in fake.of(AnswerCallbackQuery)[-2:]] == ["🗑 Удалено", "Этого уже нет."]
    await session.refresh(reminder)
    assert reminder.status == ReminderStatus.CANCELLED


def test_looks_like_reminder() -> None:
    assert reminders_router.looks_like_reminder("завтра в 9 купить молоко")
    assert not reminders_router.looks_like_reminder("купить 2 батона")
