from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup
from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, Update
from sqlalchemy import select

from assistant.bot.keyboards import FireCb
from assistant.bot.routers import reminders as reminders_router
from assistant.core.config import LIMITS
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import reminders
from assistant.core.services.recurrence import Rule
from tests.bot.fakes import callback_update, tg_user

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow
AT = int(NOW.timestamp() // 60)
_ids = itertools.count(5000)


def inaccessible_callback_update(data: str, *, user_id: int = 1) -> Update:
    """A button under a message too old for the Bot API to return (no `.text` at all)."""
    msg = InaccessibleMessage(chat=Chat(id=user_id, type="private"), message_id=next(_ids))
    query = CallbackQuery(
        id=str(next(_ids)), from_user=tg_user(user_id), chat_instance="ci", data=data, message=msg
    )
    return Update(update_id=next(_ids), callback_query=query)


async def fired_repeat(session, make_user) -> Reminder:
    user = await make_user(morning_enabled=False)
    rule = Rule(repeat=Repeat.DAILY, time_local="15:00", anchor_date=date(2026, 9, 1))
    series = await reminders.create_repeating(
        session, user, "таблетки", rule, NOW - timedelta(hours=1)
    )
    reminders.mark_delivered(series, NOW, user.timezone)
    await session.commit()
    return series


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW)


async def fired_one_off(session, make_user) -> Reminder:
    user = await make_user(morning_enabled=False)
    reminder = await reminders.create(
        session, user, "полить цветы", datetime(2026, 9, 28, 15, 30), now=NOW
    )
    reminders.mark_sent(reminder, NOW)
    await session.commit()
    return reminder


async def test_snooze_a_one_off(feed, fake, session, make_user) -> None:
    reminder = await fired_one_off(session, make_user)
    await feed(callback_update(FireCb(action="10m", id=reminder.id, at=AT).pack()))
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.PENDING
    assert reminder.due_at == NOW + timedelta(minutes=10)
    assert fake.sent_texts()[-1] == "list\n\n⏭ Перенёс на 15:10"


async def test_done_a_one_off(feed, fake, session, make_user) -> None:
    reminder = await fired_one_off(session, make_user)
    await feed(callback_update(FireCb(action="done", id=reminder.id, at=AT).pack()))
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.DONE
    assert fake.sent_texts()[-1] == "list\n\n✓ Готово"


async def test_snooze_a_repeat_until_tomorrow(feed, fake, session, make_user) -> None:
    """A daily repeat already fires at the same local time tomorrow, so «Завтра» is a no-op
    on the series itself (never a copy) — see reminders.snooze's review note: when the
    series already fires exactly at `until`, snooze returns it unchanged, no duplicate."""
    user = await make_user(morning_enabled=False)
    rule = Rule(repeat=Repeat.DAILY, time_local="15:00", anchor_date=date(2026, 9, 1))
    series = await reminders.create_repeating(
        session, user, "таблетки", rule, NOW - timedelta(hours=1)
    )
    await session.commit()
    series_id, due_before = series.id, series.due_at
    await feed(callback_update(FireCb(action="tomorrow", id=series_id, at=AT).pack()))
    session.expire_all()
    copies = (await session.scalars(select(Reminder).where(Reminder.parent_id == series_id))).all()
    assert copies == []
    series = await session.get(Reminder, series_id)
    assert series.due_at == due_before
    assert fake.sent_texts()[-1] == "list\n\n⏭ Перенёс на 29 сент., 15:00"


async def test_stale_fired_buttons_change_nothing(feed, fake, session, make_user) -> None:
    reminder = await fired_one_off(session, make_user)
    week_ago = AT - 7 * 24 * 60 - 1
    await feed(callback_update(FireCb(action="10m", id=reminder.id, at=week_ago).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert fake.of(EditMessageReplyMarkup)  # the buttons are removed
    reminder.status = ReminderStatus.CANCELLED  # deleted from the list meanwhile
    await session.commit()
    await feed(callback_update(FireCb(action="done", id=reminder.id, at=AT).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(callback_update(FireCb(action="10m", id=reminder.id, at=AT).pack(), user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.CANCELLED


async def test_pressing_someone_elses_live_reminder_changes_nothing(
    feed, fake, session, make_user
) -> None:
    """Unlike the stale/cancelled cases above, this one is still live and owned by user 1:
    a different user's press must not touch it at all."""
    reminder = await fired_one_off(session, make_user)
    await feed(callback_update(FireCb(action="10m", id=reminder.id, at=AT).pack(), user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.SENT


async def test_snooze_10m_on_a_repeat_makes_one_copy_even_on_a_double_tap(
    feed, fake, session, make_user
) -> None:
    """A double tap (or a retried callback) on «+10 мин» must not pile up duplicate copies
    of the same firing — see the dedup added to reminders.snooze."""
    series = await fired_repeat(session, make_user)
    series_id, series_due = series.id, series.due_at
    press = FireCb(action="10m", id=series_id, at=AT).pack()
    await feed(callback_update(press))
    await feed(callback_update(press))
    session.expire_all()
    copies = (await session.scalars(select(Reminder).where(Reminder.parent_id == series_id))).all()
    assert [c.due_at for c in copies] == [NOW + timedelta(minutes=10)]
    series = await session.get(Reminder, series_id)
    assert series.due_at == series_due


async def test_done_a_repeat_leaves_the_series_pending(feed, fake, session, make_user) -> None:
    series = await fired_repeat(session, make_user)
    series_id, series_due = series.id, series.due_at
    await feed(callback_update(FireCb(action="done", id=series_id, at=AT).pack()))
    series = await session.get(Reminder, series_id)
    assert series.status is ReminderStatus.PENDING
    assert series.due_at == series_due
    assert fake.sent_texts()[-1] == "list\n\n✓ Готово"


async def test_snooze_at_the_limit_shows_an_alert_and_keeps_the_reminder_sent(
    feed, fake, session, make_user
) -> None:
    reminder = await fired_one_off(session, make_user)
    for i in range(LIMITS.reminders):
        due = NOW + timedelta(days=1, minutes=i)
        session.add(
            Reminder(user_id=reminder.user_id, text=f"r{i}", due_at=due, next_attempt_at=due)
        )
    await session.commit()
    await feed(callback_update(FireCb(action="10m", id=reminder.id, at=AT).pack()))
    last = fake.of(AnswerCallbackQuery)[-1]
    assert (last.text, last.show_alert) == (
        f"Достигнут лимит — {LIMITS.reminders} напоминаний. Удали лишние.",
        True,
    )
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.SENT


async def test_edit_falls_back_to_the_reminders_own_text_without_a_readable_message(
    feed, fake, session, make_user
) -> None:
    """An InaccessibleMessage carries no `.text`: the edit must not replace the reminder
    with a bare confirmation line, so the reminder's own fire text is rebuilt instead."""
    reminder = await fired_one_off(session, make_user)
    await feed(inaccessible_callback_update(FireCb(action="done", id=reminder.id, at=AT).pack()))
    await session.refresh(reminder)
    assert reminder.status is ReminderStatus.DONE
    assert fake.sent_texts()[-1] == "⏰ Напоминание: полить цветы\n\n✓ Готово"
