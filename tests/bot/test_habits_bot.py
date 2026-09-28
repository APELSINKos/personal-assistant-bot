from __future__ import annotations

from datetime import date

from aiogram.methods import AnswerCallbackQuery, EditMessageText
from sqlalchemy import select

from assistant.bot.keyboards import HabitCb
from assistant.bot.routers.habits import habits_view, mark_view
from assistant.core.i18n import translator
from assistant.core.models import Habit, HabitMark
from assistant.core.services import habits
from assistant.core.services.habits import HabitStats
from tests.bot.fakes import callback_update, message_update

RU, EN = translator("ru"), translator("en")


def _stats(**changes: object) -> HabitStats:
    values: dict[str, object] = {
        "habit": Habit(id=7, name="Спорт"),
        "done_today": None,
        "streak": 5,
        "done_days": 12,
        "total_days": 17,
        "last_days": (None, True, True, False, True, True, True, True, None),
    }
    values.update(changes)
    return HabitStats(**values)


def test_habits_view_text() -> None:
    text, markup = habits_view([_stats()], RU)
    assert text == (
        "🎯 Твои привычки (1/10):\n"
        "\n"
        "1. Спорт — 12 из 17 дней 🔥\n"
        "    ⬜🟩🟩🟥🟩🟩🟩🟩⬜  серия: 5 дней\n"
        "\n"
        "🟩 выполнено · 🟥 пропущено · ⬜ без отметки — последние 9 дней"
    )
    assert [[b.text for b in row] for row in markup.inline_keyboard] == [
        ["✅ Отметить сегодня"],
        ["➕ Добавить", "🗑 Удалить"],
    ]


def test_habits_view_plurals_and_no_fire() -> None:
    text, _ = habits_view([_stats(streak=1, done_days=1, total_days=1)], RU)
    assert "1. Спорт — 1 из 1 дня\n" in text and "серия: 1 день" in text
    text, _ = habits_view([_stats(streak=2, total_days=21)], EN)
    assert "1. Спорт — 12 of 21 days\n" in text and "streak: 2 days" in text


def test_mark_view() -> None:
    items = [
        _stats(),
        _stats(habit=Habit(id=8, name="Чтение"), done_today=True),
        _stats(habit=Habit(id=9, name="Сон"), done_today=False),
    ]
    text, markup = mark_view(items, date(2026, 9, 28), RU)
    assert text == (
        "📅 Отметь привычки за 28 сентября\n"
        "Нажимай на привычку: ✅ выполнено → ❌ пропущено → ⬜ без отметки\n"
        "\n"
        "Выполнено: 1 из 3"
    )
    assert [row[0].text for row in markup.inline_keyboard] == [
        "⬜ Спорт",
        "✅ Чтение",
        "❌ Сон",
        "↩️ Назад",
    ]


async def test_add_habit_dialog(feed, fake) -> None:
    await feed(message_update("🎯 Привычки"))
    assert fake.sent_texts()[-1] == "🎯 Привычек пока нет. Нажми «➕ Добавить», чтобы начать."
    await feed(callback_update(HabitCb(action="add").pack()))
    assert fake.sent_texts()[-1] == "✍️ Как называется привычка? (до 50 символов)"
    await feed(message_update("x" * 51))
    assert fake.sent_texts()[-1] == "Название — это текст от 1 до 50 символов. Попробуй ещё раз:"
    await feed(message_update("Спорт"))
    assert fake.sent_texts()[-1] == "✅ Привычка «Спорт» добавлена."
    await feed(callback_update(HabitCb(action="add").pack()))
    await feed(message_update("СПОРТ"))
    assert fake.sent_texts()[-1] == "Такая привычка уже есть. Придумай другое название:"


async def test_toggle_cycle_and_foreign_habit(feed, fake, session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт")
    await session.commit()
    await feed(callback_update(HabitCb(action="mark").pack()))
    assert fake.of(EditMessageText)[-1].text.startswith("📅 Отметь привычки за ")
    toggle = HabitCb(action="toggle", id=habit.id).pack()
    seen = []
    for _ in range(3):
        await feed(callback_update(toggle))
        seen.append(fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].text)
    assert seen == ["✅ Спорт", "❌ Спорт", "⬜ Спорт"]
    assert (await session.scalars(select(HabitMark))).all() == []
    await feed(callback_update(toggle, user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."


async def test_delete_with_confirmation(feed, fake, session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт")
    await session.commit()
    await feed(callback_update(HabitCb(action="delete").pack()))
    assert fake.of(EditMessageText)[-1].text == "Какую привычку удалить?"
    await feed(callback_update(HabitCb(action="ask", id=habit.id).pack()))
    assert fake.of(EditMessageText)[-1].text == (
        "Удалить привычку «Спорт» вместе со всей статистикой?"
    )
    delete = HabitCb(action="del", id=habit.id).pack()
    await feed(callback_update(delete))
    await feed(callback_update(delete))
    assert [a.text for a in fake.of(AnswerCallbackQuery)[-2:]] == ["🗑 Удалено", "Этого уже нет."]
    assert (await session.scalars(select(Habit))).all() == []


async def test_mark_without_habits(feed, fake) -> None:
    await feed(callback_update(HabitCb(action="mark").pack()))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and answer.text == "Сначала добавь хотя бы одну привычку."
