from __future__ import annotations

from datetime import date, timedelta

from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendPhoto
from aiogram.types import Update
from aiogram.types import User as TgUser
from sqlalchemy import select

from assistant.bot.keyboards import HabitCb
from assistant.bot.routers.habits import habit_view
from assistant.core.i18n import translator, weekday_short
from assistant.core.models import Habit, HabitMark, User
from assistant.core.services import habits
from assistant.core.services.habits import HabitStats
from assistant.core.timeutil import local_today, utcnow
from tests.bot.fakes import callback_update, message_update

RU, EN = translator("ru"), translator("en")
STALE = "Эта кнопка устарела — открой раздел заново из меню."
GONE = "Этого уже нет."
TODAY = date(2026, 10, 2)


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
    habit = await habits.create(session, user, name, utcnow() - timedelta(days=days_old))
    await session.commit()
    return habit


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
    assert fake.of(EditMessageText)[-1].text.startswith("🎯 Спорт\nКаждый день · с ")
    await feed(press("list"))
    assert fake.of(EditMessageText)[-1].text.startswith("🎯 Твои привычки (1/10):")


async def test_past_days_change_a_mark_round_the_circle(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user, days_old=3)
    today = local_today("Europe/Moscow")
    await feed(press("days", habit.id))
    days = [today - timedelta(days=back) for back in range(3, -1, -1)]  # never before the habit
    assert buttons(fake) == [
        [f"{weekday_short(day.weekday(), 'ru')} {day.day} ⬜" for day in days],
        ["↩️ Назад"],
    ]
    habit_id, yesterday = habit.id, today - timedelta(days=1)
    for expected in (True, False, None):
        await feed(press("day", habit_id, yesterday.isoformat()))
        done = await session.scalar(
            select(HabitMark.done).where(HabitMark.habit_id == habit_id, HabitMark.day == yesterday)
        )
        assert done is expected
        # yesterday's button shows the mark it now has
        assert buttons(fake)[0][-2].endswith({True: "✅", False: "❌", None: "⬜"}[expected])


async def test_a_forged_or_too_early_day_is_refused(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user, days_old=3)
    today = local_today("Europe/Moscow")
    for value in ("2020-01-01", "garbage", (today + timedelta(days=1)).isoformat()):
        await feed(press("day", habit.id, value))
        assert last_answer(fake).text == STALE
    await feed(press("day", habit.id, (today - timedelta(days=5)).isoformat()))  # before the habit
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
    assert fake.of(EditMessageText)[-1].text.startswith("🏃 Спорт\n")
    for action, forged in (("emoji", "32"), ("emoji", "-1"), ("emoji", "x"), ("color", "red")):
        await feed(press(action, habit.id, forged))
        assert last_answer(fake).text == STALE
    await session.refresh(habit)
    assert (habit.emoji, habit.color) == ("🏃", "violet")


async def test_a_habit_is_renamed_from_its_card(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    owner = await session.get(User, habit.user_id)
    assert owner is not None
    await habits.create(session, owner, "Вода")
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
    assert refused.text == "⏳ Слишком много карточек подряд — попробуй через 60 с."
    monotonic[0] += 60
    await feed(press("map", habit.id))
    assert len(fake.of(SendPhoto)) == 7


async def test_a_deleted_habits_buttons_say_so(feed, fake, session, make_user) -> None:
    habit = await make_habit(session, make_user)
    await habits.delete(session, habit.user_id, habit.id)
    await session.commit()
    today = local_today("Europe/Moscow").isoformat()
    for action, value in (
        ("open", ""),
        ("map", ""),
        ("days", ""),
        ("day", today),
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
