from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from sqlalchemy import select

from assistant.bot.keyboards import HabitCb
from assistant.bot.routers import habits as habits_router
from assistant.bot.routers.habits import habits_view, mark_view
from assistant.core import timeutil
from assistant.core.i18n import translator
from assistant.core.models import Habit, HabitMark
from assistant.core.services import habits
from assistant.core.services.habits import HabitStats
from tests.bot.fakes import SERVICE_MESSAGES, callback_update, message_update

RU, EN = translator("ru"), translator("en")
STALE = "Эта кнопка устарела — открой раздел заново из меню."
# 00:30 on 2 October in Moscow, still 1 October in UTC: the day is the user's.
NOW = datetime(2026, 10, 1, 21, 30, tzinfo=UTC)
TODAY = date(2026, 10, 2)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(habits_router, "clock", lambda: NOW)
    # The router passes its `now` on everywhere: a fallback to the real clock fails the test.
    monkeypatch.setattr(timeutil, "utcnow", lambda: pytest.fail("the real clock was read"))


def _stats(**changes: object) -> HabitStats:
    values: dict[str, object] = {
        "habit": Habit(id=7, name="Спорт", weekly_goal=7, emoji="🎯"),
        "done_today": None,
        "streak": 5,
        "done_days": 12,
        "total_days": 17,
        "last_days": (None, True, True, False, True, True, True, True, None),
        "record": 5,
        "percent": 71,
        "week_done": 1,
        "week_goal": 7,
        "week": "1......",
    }
    values.update(changes)
    return HabitStats(**values)


def test_habits_view_text() -> None:
    text, markup = habits_view([_stats()], RU)
    assert text == (
        "🎯 Твои привычки (1/10):\n"
        "\n"
        "1. 🎯 Спорт — 12 из 17 дней 🔥\n"
        "    ⬜🟩🟩🟥🟩🟩🟩🟩⬜  серия: 5 дней\n"
        "\n"
        "🟩 выполнено · 🟥 пропущено · ⬜ без отметки — последние 9 дней"
    )
    assert [[b.text for b in row] for row in markup.inline_keyboard] == [
        ["🎯 Спорт"],
        ["✅ Отметить сегодня"],
        ["➕ Добавить", "🗑 Удалить"],
    ]


def test_habits_view_plurals_and_no_fire() -> None:
    text, _ = habits_view([_stats(streak=1, done_days=1, total_days=1)], RU)
    assert "1. 🎯 Спорт — 1 из 1 дня\n" in text and "серия: 1 день" in text
    text, _ = habits_view([_stats(streak=2, total_days=21)], EN)
    assert "1. 🎯 Спорт — 12 of 21 days\n" in text and "streak: 2 days" in text


def test_a_weekly_habit_shows_this_week_and_a_streak_of_weeks() -> None:
    weekly = _stats(
        habit=Habit(id=8, name="Бег", weekly_goal=3, emoji="🏃"),
        streak=5,
        week_done=2,
        week_goal=3,
    )
    text, _ = habits_view([weekly], RU)
    assert "1. 🏃 Бег — на этой неделе 2 из 3 🔥\n" in text
    assert "серия: 5 недель" in text
    text, _ = habits_view([replace(weekly, streak=1)], EN)
    assert "1. 🏃 Бег — this week 2 of 3\n" in text and "streak: 1 week" in text


def test_mark_view() -> None:
    items = [
        _stats(),
        _stats(
            habit=Habit(id=8, name="Чтение", weekly_goal=7),
            done_today=True,
            last_days=(None,) * 8 + (True,),
        ),
        _stats(
            habit=Habit(id=9, name="Сон", weekly_goal=7),
            done_today=False,
            last_days=(None,) * 8 + (False,),
        ),
    ]
    day = date(2026, 9, 28)
    text, markup = mark_view(items, day, day, RU)
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
    # A button carries the view's day and the mark after the one it shows: a tap sets what the
    # button promised, whatever the clock or the app did since.
    assert [HabitCb.unpack(row[0].callback_data) for row in markup.inline_keyboard[:3]] == [
        HabitCb(action="put", id=7, value="2026-09-28~1"),
        HabitCb(action="put", id=8, value="2026-09-28~0"),
        HabitCb(action="put", id=9, value="2026-09-28~-"),
    ]


def test_the_mark_view_of_an_earlier_day_shows_that_days_marks() -> None:
    # Drawn on the 27th, redrawn after a tap past midnight: still the 27th, with its marks.
    text, markup = mark_view([_stats()], date(2026, 9, 27), date(2026, 9, 28), RU)
    assert text.startswith("📅 Отметь привычки за 27 сентября\n")
    assert text.endswith("Выполнено: 1 из 1")
    [button] = markup.inline_keyboard[0]
    assert button.text == "✅ Спорт"
    assert HabitCb.unpack(button.callback_data) == HabitCb(action="put", id=7, value="2026-09-27~0")


def test_a_mark_button_fits_in_64_bytes_with_the_largest_id() -> None:
    for action in ("put", "dput"):
        packed = HabitCb(action=action, id=2**63 - 1, value="2026-09-28~-").pack()
        assert len(packed.encode()) <= 64, packed


async def test_add_habit_dialog(feed, fake, session) -> None:
    await feed(message_update("🎯 Привычки"))
    assert fake.sent_texts()[-1] == "🎯 Привычек пока нет. Нажми «➕ Добавить», чтобы начать."
    await feed(callback_update(HabitCb(action="add").pack()))
    assert fake.sent_texts()[-1] == "✍️ Как называется привычка? (до 50 символов)"
    await feed(message_update("x" * 51))
    assert fake.sent_texts()[-1] == "Название — это текст от 1 до 50 символов. Попробуй ещё раз:"
    await feed(message_update("Спорт"))
    assert fake.sent_texts()[-2] == "✅ Привычка «Спорт» добавлена."
    [habit] = (await session.scalars(select(Habit))).all()
    assert habit.created_on == TODAY  # the user's day by the section's clock
    # then the goal: daily until the user picks fewer days a week
    assert fake.sent_texts()[-1].startswith("🎯 Сколько раз в неделю — «Спорт»?")
    await feed(callback_update(HabitCb(action="add").pack()))
    await feed(message_update("СПОРТ"))
    assert fake.sent_texts()[-1] == "Такая привычка уже есть. Придумай другое название:"


@pytest.mark.parametrize("service", list(SERVICE_MESSAGES))
async def test_a_service_message_in_the_name_dialog_gets_no_answer(feed, fake, service) -> None:
    # The user pins a message while the bot waits for the name, say: no «Нужен текст», and the
    # dialog still takes the name.
    await feed(callback_update(HabitCb(action="add").pack()))
    asked = len(fake.calls)
    await feed(message_update(service=service))
    assert len(fake.calls) == asked
    await feed(message_update("Спорт"))
    assert fake.sent_texts()[-2] == "✅ Привычка «Спорт» добавлена."


async def test_toggle_cycle_and_foreign_habit(feed, fake, session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт", now=NOW)
    await session.commit()
    await feed(callback_update(HabitCb(action="mark").pack()))
    assert fake.of(EditMessageText)[-1].text.startswith("📅 Отметь привычки за 2 октября\n")
    # The button of the views before 2.6.1, still in the chats: it switches today's mark.
    toggle = HabitCb(action="toggle", id=habit.id).pack()
    seen = []
    for _ in range(3):
        await feed(callback_update(toggle))
        seen.append(fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].text)
    assert seen == ["✅ Спорт", "❌ Спорт", "⬜ Спорт"]
    assert (await session.scalars(select(HabitMark))).all() == []
    await feed(callback_update(toggle, user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."


async def test_the_shown_buttons_go_round_the_circle(feed, fake, session, make_user) -> None:
    user = await make_user()
    await habits.create(session, user, "Спорт", now=NOW)
    await session.commit()
    await feed(callback_update(HabitCb(action="mark").pack()))
    first = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0]
    seen = []
    for _ in range(3):
        shown = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0]
        await feed(callback_update(shown.callback_data))
        seen.append(fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].text)
    assert seen == ["✅ Спорт", "❌ Спорт", "⬜ Спорт"]
    assert (await session.scalars(select(HabitMark))).all() == []
    await feed(callback_update(first.callback_data, user_id=2))  # in another user's chat
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert (await session.scalars(select(HabitMark))).all() == []


async def test_a_mark_after_midnight_goes_to_the_day_the_view_shows(
    feed, fake, session, make_user, monkeypatch
) -> None:
    user = await make_user()
    await habits.create(session, user, "Спорт", now=NOW - timedelta(days=1))
    await session.commit()
    moment = [datetime(2026, 10, 1, 20, 59, 30, tzinfo=UTC)]  # 23:59:30 on 1 October in Moscow
    monkeypatch.setattr(habits_router, "clock", lambda: moment[0])
    await feed(callback_update(HabitCb(action="mark").pack()))
    drawn = fake.of(EditMessageText)[-1]
    assert drawn.text.startswith("📅 Отметь привычки за 1 октября\n")
    moment[0] = datetime(2026, 10, 1, 21, 0, 30, tzinfo=UTC)  # 00:00:30 on 2 October
    await feed(callback_update(drawn.reply_markup.inline_keyboard[0][0].callback_data))
    marks = (await session.execute(select(HabitMark.day, HabitMark.done))).all()
    assert [tuple(mark) for mark in marks] == [(date(2026, 10, 1), True)]
    redrawn = fake.of(EditMessageText)[-1]
    assert redrawn.text.startswith("📅 Отметь привычки за 1 октября\n")  # the same day's view
    assert redrawn.reply_markup.inline_keyboard[0][0].text == "✅ Спорт"


async def test_a_button_sets_the_mark_it_offers_after_a_mark_made_in_the_app(
    feed, fake, session, make_user
) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт", now=NOW)
    await session.commit()
    await feed(callback_update(HabitCb(action="mark").pack()))
    [button] = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0]
    assert button.text == "⬜ Спорт"
    # The app marks the habit done meanwhile: the chat's ⬜ still means «done», not «missed».
    await habits.set_mark(session, user, habit.id, TODAY, True, now=NOW)
    await session.commit()
    await feed(callback_update(button.callback_data))
    assert await session.scalar(select(HabitMark.done)) is True
    assert fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].text == "✅ Спорт"


async def test_a_forged_or_stale_mark_button_is_refused(feed, fake, session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт", now=NOW)  # begun today, 2 October
    await session.commit()
    for value in (
        "2026-10-02",  # no mark to set
        "2026-10-02~x",
        "2026-10-02~1~1",
        "garbage~1",
        "2026-10-03~1",  # tomorrow
        "2026-09-25~1",  # a week ago: no view offers that day any more
        "2026-10-01~1",  # yesterday, before the habit began
    ):
        await feed(callback_update(HabitCb(action="put", id=habit.id, value=value).pack()))
        assert fake.of(AnswerCallbackQuery)[-1].text == STALE, value
    assert (await session.scalars(select(HabitMark))).all() == []


async def test_delete_with_confirmation(feed, fake, session, make_user) -> None:
    user = await make_user()
    habit = await habits.create(session, user, "Спорт", now=NOW)
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


async def test_old_buttons_never_hit_a_newer_habit(feed, fake, session, make_user) -> None:
    user = await make_user()
    first = await habits.create(session, user, "Спорт", now=NOW)
    await session.commit()
    await feed(callback_update(HabitCb(action="mark").pack()))
    old_toggle = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].callback_data
    await feed(callback_update(HabitCb(action="ask", id=first.id).pack()))
    old_delete = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].callback_data
    await feed(callback_update(old_delete))
    assert fake.of(AnswerCallbackQuery)[-1].text == "🗑 Удалено"
    second = await habits.create(session, user, "Чтение", now=NOW)
    await session.commit()
    assert second.id != first.id  # ids of deleted habits are never reused
    await feed(callback_update(old_toggle))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(callback_update(old_delete))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert [h.name for h in (await session.scalars(select(Habit))).all()] == ["Чтение"]
    assert (await session.scalars(select(HabitMark))).all() == []


async def test_toggle_outside_the_habit_days_answers_like_a_stale_button(
    feed, fake, session, make_user
) -> None:
    user = await make_user()
    # Created "tomorrow" from the user's point of view, e.g. after moving west that day.
    habit = Habit(user_id=user.id, name="Спорт", created_on=TODAY + timedelta(days=1))
    session.add(habit)
    await session.commit()
    await feed(callback_update(HabitCb(action="toggle", id=habit.id).pack()))
    answer = fake.of(AnswerCallbackQuery)[-1]
    assert answer.text == "Эта кнопка устарела — открой раздел заново из меню."
    assert fake.of(EditMessageText)[-1].text.startswith("📅 Отметь привычки за 2 октября\n")
    assert not any(text.startswith("⚠️") for text in fake.sent_texts())
    assert (await session.scalars(select(HabitMark))).all() == []


@pytest.mark.parametrize(
    ("streak", "russian", "english"),
    [
        (1, "серия: 1 неделя", "streak: 1 week"),
        (2, "серия: 2 недели", "streak: 2 weeks"),
        (5, "серия: 5 недель", "streak: 5 weeks"),
    ],
)
def test_a_weekly_streak_has_its_russian_and_english_forms(
    streak: int, russian: str, english: str
) -> None:
    weekly = _stats(
        habit=Habit(id=8, name="Бег", weekly_goal=3, emoji="🏃"),
        streak=streak,
        week_done=2,
        week_goal=3,
    )
    assert russian in habits_view([weekly], RU)[0]
    assert english in habits_view([weekly], EN)[0]
