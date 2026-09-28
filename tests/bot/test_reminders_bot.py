from __future__ import annotations

from datetime import UTC, datetime

from aiogram.methods import AnswerCallbackQuery, EditMessageText
from sqlalchemy import select

from assistant.bot import texts
from assistant.bot.keyboards import ReminderCb
from assistant.core.models import Reminder, ReminderStatus
from assistant.core.services import reminders
from tests.bot.fakes import callback_update, message_update

ASK_WHEN = (
    "Когда напомнить? Примеры:\n"
    "• 18:30 — сегодня (или завтра, если время уже прошло)\n"
    "• 25.09 18:30 — в этом году\n"
    "• 25.09.2027 18:30 — точная дата"
)


async def test_add_reminder_dialog(feed, fake, session) -> None:
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Активных напоминаний нет. Нажми «➕ Добавить», чтобы создать."
    )
    await feed(callback_update(ReminderCb(action="add").pack()))
    assert fake.sent_texts()[-1] == "✍️ О чём напомнить? (до 200 символов)"
    await feed(message_update("   "))
    assert fake.sent_texts()[-1] == "Нужен текст от 1 до 200 символов. Попробуй ещё раз:"
    await feed(message_update("купить молоко"))
    assert fake.sent_texts()[-1] == ASK_WHEN
    await feed(message_update(None, sticker=True))
    assert fake.sent_texts()[-1] == "Нужен текст. Напиши время, например 18:30 или 25.09 18:30."
    await feed(message_update("завтра"))
    assert fake.sent_texts()[-1] == "Не понял время. " + ASK_WHEN
    await feed(message_update("01.01.2020 10:00"))
    assert fake.sent_texts()[-1] == "Это время уже прошло. Укажи момент в будущем:"
    await feed(message_update("25.09.2099 18:30"))
    assert fake.sent_texts()[-1] == "✅ Напомню 25 сентября 2099 в 18:30: купить молоко"
    stored = (await session.scalars(select(Reminder))).one()
    assert stored.due_at == datetime(2099, 9, 25, 15, 30, tzinfo=UTC)
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Твои напоминания (1/20):\n\n1. 25 сент. 2099, 18:30 — купить молоко"
    )


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
    assert fake.of(EditMessageText)[-1].text.startswith("⏰ Активных напоминаний нет")


async def test_limit_of_twenty(feed, fake, session, make_user) -> None:
    user = await make_user()
    for day in range(1, 21):
        await reminders.create(session, user, f"r{day}", datetime(2099, 1, day, 10, 0))
    await session.commit()
    await feed(callback_update(ReminderCb(action="add").pack()))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and answer.text == "Достигнут лимит — 20 напоминаний. Удали лишние."


def test_moment_formatting() -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    moment = datetime(2026, 9, 25, 15, 30, tzinfo=UTC)
    assert texts.short_moment(moment, "Europe/Moscow", "ru", now) == "25 сент., 18:30"
    assert texts.short_moment(moment, "Europe/Moscow", "en", now) == "25 Sep, 18:30"
