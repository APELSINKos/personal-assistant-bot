from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup
from sqlalchemy import select

from assistant.bot.keyboards import FireCb
from assistant.bot.routers import reminders as reminders_router
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import reminders
from assistant.core.services.recurrence import Rule
from tests.bot.fakes import callback_update

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow
AT = int(NOW.timestamp() // 60)


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
