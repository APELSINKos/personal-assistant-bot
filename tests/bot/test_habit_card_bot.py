from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendPhoto
from aiogram.types import Update
from aiogram.types import User as TgUser
from sqlalchemy import select

from assistant.bot.keyboards import HabitCb
from assistant.bot.routers import habits as habits_router
from assistant.bot.routers.habits import habit_view
from assistant.core import timeutil
from assistant.core.i18n import translator
from assistant.core.models import Habit, HabitMark, User
from assistant.core.services import habits
from assistant.core.services.habits import HabitStats
from tests.bot.fakes import callback_update, message_update

RU, EN = translator("ru"), translator("en")
STALE = "Эта кнопка устарела — открой раздел заново из меню."
GONE = "Этого уже нет."
TODAY = date(2026, 10, 2)
# 00:30 on TODAY in Moscow, still 1 October in UTC: the day is the user's.
NOW = datetime(2026, 10, 1, 21, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(habits_router, "clock", lambda: NOW)
    # The router passes its `now` on everywhere: a fallback to the real clock fails the test.
    monkeypatch.setattr(timeutil, "utcnow", lambda: pytest.fail("the real clock was read"))


def press(action: str, habit_id: int = 0, value: str = "") -> Update:
    return callback_update(HabitCb(action=action, id=habit_id, value=value).pack())


def buttons(fake) -> list[list[str]]:
    markup = fake.of(EditMessageText)[-1].reply_markup
    return [[button.text for button in row] for row in markup.inline_keyboard]


def last_answer(fake) -> AnswerCallbackQuery:
    return fake.of(AnswerCallbackQuery)[-1]


def stats(habit: Habit, **values: object) -> HabitStats:
    base: dict[str, object] = {
        "habit": habit,
        "today": TODAY,
        "done_today": True,
        "streak": 42,
        "done_days": 200,
        "total_days": 240,
        "last_days": (True,) * 9,
        "record": 58,
        "percent": 87,
        "week_done": 5,
        "week_goal": 7,
        "week": "11111..",
    }
    base.update(values)
    return HabitStats(**base)  # type: ignore[arg-type]


async def make_habit(session, make_user, *, days_old: int = 0, name: str = "Спорт") -> Habit:
    user = await make_user()
    habit = await habits.create(session, user, name, NOW - timedelta(days=days_old))
    await session.commit()
    return habit


def new_card(emoji: str = "🎯") -> str:
    """The card of a daily habit begun on TODAY, a Friday: its week has three days left."""
    return (
        f"{emoji} Спорт\n"
        "Каждый день · с 2 октября\n"
        "\n"
        "🔥 Серия: 0 дней\n"
        "🏆 Рекорд: 0 дней\n"
        "📊 За год: 0%\n"
        "📅 Эта неделя: 0 из 3"
    )


def test_a_habits_card_tells_its_goal_streak_record_year_and_week() -> None:
    daily = Habit(id=7, name="Спорт", emoji="💪", weekly_goal=7, created_on=date(2026, 2, 3))
    text, markup = habit_view(stats(daily), TODAY, RU)
    assert text == (
        "💪 Спорт\n"
        "Каждый день · с 3 февраля\n"
        "\n"
        "🔥 Серия: 42 дня\n"
        "🏆 Рекорд: 58 дней\n"
        "📊 За год: 87%\n"
        "📅 Эта неделя: 5 из 7"
    )
    assert [[button.text for button in row] for row in markup.inline_keyboard] == [
        ["📊 Карта года", "📅 Прошлые дни"],
        ["🎯 Цель", "🎨 Эмодзи и цвет"],
        ["✏️ Название", "🗑 Удалить"],
        ["↩️ К привычкам"],
    ]
    # Begun last year: the first day names its year.
    weekly = Habit(id=8, name="Run", emoji="🏃", weekly_goal=3, created_on=date(2025, 2, 3))
    text, _ = habit_view(
        stats(weekly, streak=1, record=4, percent=75, week_done=2, week_goal=3), TODAY, EN
    )
    assert text == (
        "🏃 Run\n"
        "3 times a week · since February 3, 2025\n"
        "\n"
        "🔥 Streak: 1 week\n"
        "🏆 Record: 4 weeks\n"
        "📊 Past year: 75%\n"
        "📅 This week: 2 of 3"
    )


async def test_the_list_opens_a_habits_card(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    await feed(press("open", habit.id))
    assert fake.of(EditMessageText)[-1].text == new_card()
    await feed(press("list"))
    assert fake.of(EditMessageText)[-1].text.startswith("🎯 Твои привычки (1/10):")


async def test_past_days_change_a_mark_round_the_circle(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user, days_old=3)
    await feed(press("days", habit.id))
    assert buttons(fake) == [
        ["вт 29 ⬜", "ср 30 ⬜", "чт 1 ⬜", "пт 2 ⬜"],  # never before the habit
        ["↩️ Назад"],
    ]
    habit_id, yesterday = habit.id, date(2026, 10, 1)
    for expected in (True, False, None):
        shown = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][-2]
        await feed(callback_update(shown.callback_data))
        done = await session.scalar(
            select(HabitMark.done).where(HabitMark.habit_id == habit_id, HabitMark.day == yesterday)
        )
        assert done is expected
        # yesterday's button shows the mark it now has
        assert buttons(fake)[0][-2].endswith({True: "✅", False: "❌", None: "⬜"}[expected])


async def test_an_old_day_button_still_switches_the_mark(feed, fake, session, make_user) -> None:
    # The button of «📅 Прошлые дни» before 2.6.1, still in the chats: it carries only its day
    # and switches the mark that day has.
    habit = await make_habit(session, make_user, days_old=3)
    yesterday = date(2026, 10, 1)
    for expected in (True, False, None):
        await feed(press("day", habit.id, yesterday.isoformat()))
        assert await session.scalar(select(HabitMark.done)) is expected
        assert buttons(fake)[0][-2].endswith({True: "✅", False: "❌", None: "⬜"}[expected])


async def test_a_past_day_gets_the_mark_its_button_offers_after_the_app(
    feed, fake, session, make_user
) -> None:
    habit = await make_habit(session, make_user, days_old=3)
    await feed(press("days", habit.id))
    button = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][2]
    assert button.text == "чт 1 ⬜"
    # The app marks 1 October done meanwhile: the chat's ⬜ still means «done», not «missed».
    owner = await session.get(User, habit.user_id)
    assert owner is not None
    await habits.set_mark(session, owner, habit.id, date(2026, 10, 1), True, now=NOW)
    await session.commit()
    await feed(callback_update(button.callback_data))
    assert await session.scalar(select(HabitMark.done)) is True
    assert buttons(fake)[0][2] == "чт 1 ✅"


async def test_past_days_drawn_before_midnight_mark_the_days_they_show(
    feed, fake, session, make_user, monkeypatch
) -> None:
    habit = await make_habit(session, make_user, days_old=8)
    moment = [datetime(2026, 10, 1, 20, 59, 30, tzinfo=UTC)]  # 23:59:30 on 1 October in Moscow
    monkeypatch.setattr(habits_router, "clock", lambda: moment[0])
    await feed(press("days", habit.id))
    drawn = fake.of(EditMessageText)[-1].reply_markup.inline_keyboard
    assert [button.text for button in drawn[0] + drawn[1]] == [
        "пт 25 ⬜",
        "сб 26 ⬜",
        "вс 27 ⬜",
        "пн 28 ⬜",
        "вт 29 ⬜",
        "ср 30 ⬜",
        "чт 1 ⬜",
    ]
    moment[0] = datetime(2026, 10, 1, 21, 0, 30, tzinfo=UTC)  # 00:00:30 on 2 October
    await feed(callback_update(drawn[1][2].callback_data))  # 1 October, yesterday by now
    marks = (await session.execute(select(HabitMark.day, HabitMark.done))).all()
    assert [tuple(mark) for mark in marks] == [(date(2026, 10, 1), True)]
    await feed(callback_update(drawn[0][0].callback_data))  # 25 September, a week ago by now
    assert last_answer(fake).text == STALE
    assert len((await session.scalars(select(HabitMark))).all()) == 1


async def test_a_forged_or_stale_past_day_button_is_refused(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user, days_old=3)  # begun on 29 September
    owner = await session.get(User, habit.user_id)
    assert owner is not None
    # Begun on 21 September: the habit itself would take each of its days below.
    older = await habits.create(session, owner, "Чтение", NOW - timedelta(days=11))
    await session.commit()
    for habit_id, value in (
        (habit.id, "2026-10-01"),  # no mark to set
        (habit.id, "2026-10-01~x"),
        (habit.id, "garbage~1"),
        (habit.id, "2026-10-03~1"),  # tomorrow
        (habit.id, "2026-09-28~1"),  # before the habit
        (older.id, "2026-09-25~1"),  # a week ago
        (older.id, "2026-09-21~1"),
    ):
        await feed(press("dput", habit_id, value))
        assert last_answer(fake).text == STALE, value
    assert (await session.scalars(select(HabitMark))).all() == []


async def test_a_forged_or_too_early_day_is_refused(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user, days_old=3)
    for value in ("2020-01-01", "garbage", "2026-10-03"):  # 3 October is tomorrow
        await feed(press("day", habit.id, value))
        assert last_answer(fake).text == STALE
    await feed(press("day", habit.id, "2026-09-27"))  # before the habit
    assert last_answer(fake).text == STALE
    assert (await session.scalars(select(HabitMark))).all() == []


async def test_the_goal_is_picked_from_buttons(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    await feed(press("goal", habit.id))
    assert fake.of(EditMessageText)[-1].text.startswith("🎯 Сколько раз в неделю — «Спорт»?")
    assert buttons(fake) == [
        ["• Каждый день"],
        ["6 раз в неделю", "5 раз в неделю", "4 раза в неделю"],
        ["3 раза в неделю", "2 раза в неделю", "1 раз в неделю"],
        ["↩️ Назад"],
    ]
    await feed(press("setgoal", habit.id, "3"))
    await session.refresh(habit)
    assert habit.weekly_goal == 3
    text = fake.of(EditMessageText)[-1].text
    assert "3 раза в неделю · с " in text and "🔥 Серия: 0 недель" in text
    for forged in ("9", "0", "²", "", "07"):
        await feed(press("setgoal", habit.id, forged))
        assert last_answer(fake).text == STALE
    await session.refresh(habit)
    assert habit.weekly_goal == 3


async def test_emoji_and_colour_come_from_the_set(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    await feed(press("style", habit.id))
    rows = buttons(fake)
    assert rows[0] == ["💪", "🏃", "🚴", "🏊"] and len(rows) == 9  # 8 rows of 4 and «Назад»
    await feed(press("emoji", habit.id, "1"))
    assert buttons(fake) == [["🟢", "🔵", "🟣", "🔴"], ["🟠", "🟡", "🟤", "⚪"], ["↩️ Назад"]]
    await feed(press("color", habit.id, "violet"))
    await session.refresh(habit)
    assert (habit.emoji, habit.color) == ("🏃", "violet")
    assert fake.of(EditMessageText)[-1].text == new_card("🏃")
    for action, forged in (("emoji", "32"), ("emoji", "-1"), ("emoji", "x"), ("color", "red")):
        await feed(press(action, habit.id, forged))
        assert last_answer(fake).text == STALE
    await session.refresh(habit)
    assert (habit.emoji, habit.color) == ("🏃", "violet")


async def test_a_habit_is_renamed_from_its_card(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    owner = await session.get(User, habit.user_id)
    assert owner is not None
    await habits.create(session, owner, "Вода", now=NOW)
    await session.commit()
    await feed(press("rename", habit.id))
    assert fake.sent_texts()[-1] == "✍️ Новое название для «Спорт» (до 50 символов):"
    await feed(message_update("вода"))
    assert fake.sent_texts()[-1] == "Такая привычка уже есть. Придумай другое название:"
    await feed(message_update("Бег"))
    assert fake.sent_texts()[-1] == "✅ Готово: «Бег»."
    await session.refresh(habit)
    assert habit.name == "Бег"


async def test_the_year_map_comes_as_a_photo(feed, fake, session, make_user) -> None:
    fake.results[GetMe] = TgUser(id=42, is_bot=True, first_name="Bot", username="assistant_bot")
    habit = await make_habit(session, make_user)
    await feed(press("map", habit.id))
    [photo] = fake.of(SendPhoto)
    assert photo.chat_id == 1
    assert photo.caption == "🎯 Спорт — 0 дней подряд"
    assert photo.photo.data[:2] == b"\xff\xd8"


async def test_six_cards_a_minute(feed, fake, session, make_user, monotonic) -> None:
    fake.results[GetMe] = TgUser(id=42, is_bot=True, first_name="Bot", username="assistant_bot")
    habit = await make_habit(session, make_user)
    for _ in range(6):
        await feed(press("map", habit.id))
    await feed(press("map", habit.id))
    assert len(fake.of(SendPhoto)) == 6
    refused = last_answer(fake)
    assert refused.show_alert
    assert refused.text == "⏳ Слишком много картинок подряд — попробуй через 60 с."
    monotonic[0] += 60
    await feed(press("map", habit.id))
    assert len(fake.of(SendPhoto)) == 7


async def test_a_deleted_habits_buttons_say_so(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    await habits.delete(session, habit.user_id, habit.id)
    await session.commit()
    for action, value in (
        ("open", ""),
        ("map", ""),
        ("days", ""),
        ("day", TODAY.isoformat()),
        ("dput", f"{TODAY.isoformat()}~1"),
        ("put", f"{TODAY.isoformat()}~1"),
        ("goal", ""),
        ("setgoal", "3"),
        ("style", ""),
        ("emoji", "0"),
        ("color", "mint"),
        ("rename", ""),
    ):
        await feed(press(action, habit.id, value))
        assert last_answer(fake).text == GONE, action
        assert fake.of(EditMessageText)[-1].text.startswith("🎯 Привычек пока нет.")
