from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from aiogram.exceptions import (
    ClientDecodeError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import EditMessageText, SendMessage
from sqlalchemy import select

from assistant.bot import scheduler as scheduler_module
from assistant.bot.keyboards import FireCb, WeatherCb
from assistant.bot.replies import NO_PREVIEW
from assistant.bot.routers import weather as weather_router
from assistant.bot.scheduler import Scheduler
from assistant.core.clients.cbr import CbrClient, Rates
from assistant.core.models import FsmState, Habit, Reminder, ReminderStatus, Repeat, ShareCard
from assistant.core.services import reminders
from assistant.core.services.recurrence import Rule
from tests.bot.fakes import callback_update
from tests.stubs import FORECAST_NOW, StubCbr, StubMeteo

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # 15:00 in Moscow
METHOD = SendMessage(chat_id=1, text="x")


@pytest.fixture
def scheduler(bot, sessionmaker, meteo, cbr) -> Scheduler:
    return Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: NOW)


async def add_reminder(
    session, user_id: int = 1, *, ago: timedelta = timedelta(minutes=1), text: str = "полить цветы"
) -> Reminder:
    due = NOW - ago
    reminder = Reminder(user_id=user_id, text=text, due_at=due, next_attempt_at=due)
    session.add(reminder)
    await session.commit()
    return reminder


async def reload(session, obj):
    await session.refresh(obj)
    return obj


async def test_delivers_due_reminder(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    await add_reminder(session, ago=-timedelta(minutes=5), text="future")
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы"]
    reminder = await reload(session, reminder)
    assert reminder.status == ReminderStatus.SENT and reminder.sent_at == NOW


@pytest.mark.parametrize(
    ("ago", "suffix"),
    [
        (timedelta(minutes=5), ""),
        (timedelta(minutes=30), " (было на 14:30)"),
        (timedelta(hours=20), " (было на 27 сент., 19:00)"),
    ],
)
async def test_late_mark(scheduler, session, make_user, fake, ago, suffix) -> None:
    await make_user(morning_enabled=False)
    await add_reminder(session, ago=ago)
    await scheduler.deliver_reminders(NOW)
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы" + suffix]


async def test_retry_after_does_not_count_and_stops_the_batch(
    scheduler, session, make_user, fake
) -> None:
    await make_user(morning_enabled=False)
    first = await add_reminder(session, ago=timedelta(minutes=2))
    second = await add_reminder(session, ago=timedelta(minutes=1))
    fake.errors.append(
        TelegramRetryAfter(method=METHOD, message="Too Many Requests", retry_after=7)
    )
    assert await scheduler.deliver_reminders(NOW) == 0
    assert len(fake.calls) == 1
    first, second = await reload(session, first), await reload(session, second)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 0)
    assert first.next_attempt_at == NOW + timedelta(seconds=7)
    assert second.status == ReminderStatus.PENDING


async def test_network_errors_back_off_then_fail(
    scheduler, session, make_user, fake, caplog
) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    moment = NOW
    delays = []
    for attempt in range(1, reminders.MAX_FAILURES + 1):
        error = (
            TelegramNetworkError(method=METHOD, message="timeout")
            if attempt % 2
            else TelegramServerError(method=METHOD, message="Bad Gateway")
        )
        fake.errors.append(error)
        await scheduler.deliver_reminders(moment)
        reminder = await reload(session, reminder)
        if attempt < reminders.MAX_FAILURES:
            assert (reminder.status, reminder.attempts) == (ReminderStatus.PENDING, attempt)
            delays.append((reminder.next_attempt_at - moment).total_seconds())
            moment = reminder.next_attempt_at
    assert delays == [30, 60, 300, 900, 3600, 10800]
    assert (reminder.status, reminder.attempts) == (ReminderStatus.FAILED, 7)
    gave_up = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert gave_up == [f"reminder {reminder.id} gave up after 7 attempts: network: timeout"]


async def test_blocked_user(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    first = await add_reminder(session, ago=timedelta(minutes=2))
    second = await add_reminder(session, ago=timedelta(minutes=1))
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user")
    )
    await scheduler.deliver_reminders(NOW)
    assert len(fake.calls) == 1
    assert (await reload(session, first)).status == ReminderStatus.FAILED
    assert (await reload(session, second)).status == ReminderStatus.PENDING
    assert (await reload(session, user)).bot_blocked
    assert await scheduler.deliver_reminders(NOW + timedelta(minutes=1)) == 0
    assert len(fake.calls) == 1


async def test_bad_request_fails_without_blocking(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    await scheduler.deliver_reminders(NOW)
    assert (await reload(session, reminder)).status == ReminderStatus.FAILED
    assert not (await reload(session, user)).bot_blocked


@pytest.mark.parametrize(
    "error",
    [
        ClientDecodeError("failed to decode", ValueError("bad json"), b"<html>"),
        TelegramNetworkError(method=METHOD, message="timeout"),
        TelegramServerError(method=METHOD, message="Bad Gateway"),
    ],
)
async def test_network_failure_stops_the_batch(scheduler, session, make_user, fake, error) -> None:
    await make_user(id=1, morning_enabled=False)
    await make_user(id=2, morning_enabled=False)
    first = await add_reminder(session, user_id=1, ago=timedelta(minutes=2), text="полить цветы")
    second = await add_reminder(session, user_id=2, ago=timedelta(minutes=1), text="call mom")
    fake.errors.append(error)
    assert await scheduler.deliver_reminders(NOW) == 0
    # Only the first one was attempted; a dropping network must not stall the tick with a
    # timeout per reminder. The second stays due, untouched, for the next tick.
    assert fake.sent_texts() == ["⏰ Напоминание: полить цветы"]
    first = await reload(session, first)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 1)
    assert first.next_attempt_at == NOW + timedelta(seconds=reminders.BACKOFF[0])
    second = await reload(session, second)
    assert (second.status, second.attempts) == (ReminderStatus.PENDING, 0)
    assert await scheduler.deliver_reminders(NOW + timedelta(seconds=1)) == 1
    assert (await reload(session, second)).status == ReminderStatus.SENT


async def test_unexpected_error_for_one_reminder_does_not_stop_the_batch(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(id=1, morning_enabled=False)
    await make_user(id=2, morning_enabled=False)
    first = await add_reminder(session, user_id=1, ago=timedelta(minutes=2), text="broken")
    await add_reminder(session, user_id=2, ago=timedelta(minutes=1), text="ok")
    original = scheduler_module.reminder_text

    def flaky(reminder, user, shown, now, t):
        if reminder.text == "broken":
            raise RuntimeError("boom")
        return original(reminder, user, shown, now, t)

    monkeypatch.setattr(scheduler_module, "reminder_text", flaky)
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: ok"]
    first = await reload(session, first)
    assert (first.status, first.attempts) == (ReminderStatus.PENDING, 1)
    assert first.next_attempt_at == NOW + timedelta(seconds=reminders.BACKOFF[0])


TOMORROW_1500 = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)  # 15:00 in Moscow


def change_while_sending(monkeypatch, scheduler, sessionmaker, change) -> None:
    """The first message on its way waits for `change`, committed from a session of its own:
    the app, or a button under a message Telegram has already delivered."""
    send = scheduler._send

    async def sending(*args, **kwargs):
        monkeypatch.setattr(scheduler, "_send", send)
        async with sessionmaker() as app:
            await change(app)
            await app.commit()
        return await send(*args, **kwargs)

    monkeypatch.setattr(scheduler, "_send", sending)


def moved_to_tomorrow(user, reminder):
    async def change(app) -> None:
        when = datetime(2026, 9, 29, 15, 0)
        await reminders.update_reminder(app, user, reminder.id, when_local=when, now=NOW)

    return change


async def test_a_reminder_moved_while_it_is_sent_fires_at_its_new_time(
    scheduler, session, sessionmaker, make_user, fake, monkeypatch
) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    change_while_sending(monkeypatch, scheduler, sessionmaker, moved_to_tomorrow(user, reminder))
    assert await scheduler.deliver_reminders(NOW) == 1
    reminder = await reload(session, reminder)
    assert (reminder.status, reminder.due_at) == (ReminderStatus.PENDING, TOMORROW_1500)
    assert await scheduler.deliver_reminders(TOMORROW_1500) == 1
    assert (await reload(session, reminder)).status == ReminderStatus.SENT


async def test_a_move_during_a_failed_send_keeps_the_new_time(
    scheduler, session, sessionmaker, make_user, fake, monkeypatch
) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    change_while_sending(monkeypatch, scheduler, sessionmaker, moved_to_tomorrow(user, reminder))
    fake.errors.append(TelegramNetworkError(method=METHOD, message="timeout"))
    assert await scheduler.deliver_reminders(NOW) == 0
    reminder = await reload(session, reminder)
    # Not a retry in 30 seconds: the failed send was of the old time.
    assert (reminder.status, reminder.attempts) == (ReminderStatus.PENDING, 0)
    assert reminder.next_attempt_at == TOMORROW_1500


async def test_a_move_while_the_bot_gets_blocked_keeps_the_new_time(
    scheduler, session, sessionmaker, make_user, fake, monkeypatch
) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    change_while_sending(monkeypatch, scheduler, sessionmaker, moved_to_tomorrow(user, reminder))
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user")
    )
    assert await scheduler.deliver_reminders(NOW) == 0
    reminder = await reload(session, reminder)
    assert (reminder.status, reminder.due_at) == (ReminderStatus.PENDING, TOMORROW_1500)
    assert (await reload(session, user)).bot_blocked


async def test_a_snooze_pressed_while_it_is_sent_is_kept(
    scheduler, session, sessionmaker, make_user, fake, monkeypatch
) -> None:
    user = await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    until = NOW + timedelta(minutes=10)

    async def snoozed(app) -> None:
        await reminders.snooze(app, user, reminder.id, until, NOW)

    change_while_sending(monkeypatch, scheduler, sessionmaker, snoozed)
    assert await scheduler.deliver_reminders(NOW) == 1
    reminder = await reload(session, reminder)
    assert (reminder.status, reminder.due_at) == (ReminderStatus.PENDING, until)


async def test_send_passes_the_link_preview_options(scheduler, fake) -> None:
    assert (await scheduler._send(1, "open-meteo.com", link_preview_options=NO_PREVIEW)).ok
    assert (await scheduler._send(1, "⏰ Напоминание: полить цветы")).ok
    without_preview, as_before = fake.of(SendMessage)
    assert without_preview.link_preview_options == NO_PREVIEW
    assert as_before.link_preview_options is None


# 23:30 Moscow = 20:30 UTC; the window lasts until 00:30 of the next local day.
AT_2345 = datetime(2026, 9, 28, 20, 45, tzinfo=UTC)
AT_0015 = datetime(2026, 9, 28, 21, 15, tzinfo=UTC)


async def test_digest_window_crossing_midnight_sends_once(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    assert await scheduler.send_digests(AT_2345) == 1
    assert fake.sent_texts()[0].startswith("☀️ Доброе утро, Test!")
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)
    assert await scheduler.send_digests(AT_0015) == 0
    assert len(fake.calls) == 1


async def test_digest_retries_after_network_error_inside_the_window(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(TelegramNetworkError(method=METHOD, message="timeout"))
    assert await scheduler.send_digests(AT_2345) == 0
    assert (await reload(session, user)).last_morning_date is None
    assert await scheduler.send_digests(AT_0015) == 1
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)


AT_0800 = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)  # the usual digest's time in Moscow
UNAVAILABLE = "🌤 Погода временно недоступна"


def buttons(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.inline_keyboard]


async def test_the_digest_brings_the_forecast_buttons_without_a_preview(
    scheduler, make_user, fake, feed, monkeypatch
) -> None:
    monkeypatch.setattr(weather_router, "clock", lambda: FORECAST_NOW)
    await make_user()
    assert await scheduler.send_digests(AT_0800) == 1
    [digest] = fake.of(SendMessage)
    assert digest.text.split("\n")[3:6] == [
        "🌤 Москва: +10°C, малооблачно · днём до +13°C",
        "🚲 Сегодня хороший день для велосипеда",
        "Данные о погоде: open-meteo.com",
    ]
    assert digest.link_preview_options.is_disabled
    assert buttons(digest) == [["🕐 По часам", "📅 Неделя"]]
    hours = digest.reply_markup.inline_keyboard[0][0].callback_data
    assert hours == WeatherCb(view="hours", new=1).pack()
    # A press sends the hours as a message of its own: the digest stays as it is.
    await feed(callback_update(hours))
    assert fake.of(EditMessageText) == []
    assert fake.of(SendMessage)[-1].text.startswith("🕐 Москва — по часам\n\n11:00 🌤 +11°C\n")


async def test_the_digest_waits_ten_minutes_for_the_weather(
    scheduler, session, make_user, fake, meteo, caplog
) -> None:
    user = await make_user()
    meteo.fail = True
    # Every tick of the first ten minutes asks again and sends nothing.
    for moment in (AT_0800, AT_0800 + timedelta(seconds=20), AT_0800 + timedelta(seconds=599)):
        assert await scheduler.send_digests(moment) == 0
    assert fake.calls == [] and (await reload(session, user)).last_morning_date is None
    assert "not delivered" not in caplog.text  # waiting is no failure
    # Then the digest goes without the weather: neither its source nor its buttons.
    assert await scheduler.send_digests(AT_0800 + timedelta(minutes=10)) == 1
    [digest] = fake.of(SendMessage)
    assert digest.text.split("\n")[3:5] == [UNAVAILABLE, ""]
    assert "open-meteo.com" not in digest.text and digest.reply_markup is None
    assert digest.link_preview_options.is_disabled
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)


async def test_the_weather_back_within_the_wait_comes_with_the_digest(
    scheduler, make_user, fake, meteo
) -> None:
    await make_user()
    meteo.fail = True
    assert await scheduler.send_digests(AT_0800) == 0
    meteo.fail = False
    assert await scheduler.send_digests(AT_0800 + timedelta(seconds=20)) == 1  # the next tick
    [digest] = fake.of(SendMessage)
    assert digest.text.split("\n")[3] == "🌤 Москва: +10°C, малооблачно · днём до +13°C"
    assert buttons(digest) == [["🕐 По часам", "📅 Неделя"]]


async def test_a_digest_late_in_its_window_does_not_wait(scheduler, make_user, fake, meteo) -> None:
    # The bot was down at 08:00 and is back at 08:30: the window is still open, the wait is over.
    await make_user()
    meteo.fail = True
    assert await scheduler.send_digests(AT_0800 + timedelta(minutes=30)) == 1
    assert fake.sent_texts()[0].split("\n")[3] == UNAVAILABLE


async def test_the_wait_of_a_window_across_midnight(
    scheduler, session, make_user, fake, meteo
) -> None:
    user = await make_user(morning_time="23:55")
    meteo.fail = True
    at_2355 = datetime(2026, 9, 28, 20, 55, tzinfo=UTC)
    for moment in (at_2355, at_2355 + timedelta(minutes=9)):  # 00:04 of the next day
        assert await scheduler.send_digests(moment) == 0
    assert await scheduler.send_digests(at_2355 + timedelta(minutes=10)) == 1
    assert (await reload(session, user)).last_morning_date == date(2026, 9, 28)


class CountingCbr(StubCbr):
    """Counts the requests for the day's rates: every reading of the day makes one."""

    def __init__(self) -> None:
        super().__init__()
        self.requests = 0

    async def daily(self) -> Rates:
        self.requests += 1
        return await super().daily()


async def test_a_waiting_digest_asks_for_nothing_but_the_weather(
    bot, sessionmaker, make_user, fake, meteo
) -> None:
    # The bank's mirror may hang while Open-Meteo is down. Were the rates asked for, every
    # waiting digest would cost every tick a timeout, and the reminders would wait behind them.
    cbr = CountingCbr()
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: NOW)
    await make_user(id=1)
    await make_user(id=2)
    meteo.fail = True
    for moment in (AT_0800, AT_0800 + timedelta(seconds=20)):
        assert await scheduler.send_digests(moment) == 0
    assert cbr.requests == 0  # and so the day was not read at all
    meteo.fail = False
    assert await scheduler.send_digests(AT_0800 + timedelta(seconds=40)) == 2
    assert cbr.requests == 2


async def test_a_hanging_bank_costs_a_digest_pass_one_timeout(
    bot, sessionmaker, make_user, fake, meteo
) -> None:
    # The first digest waits out the mirror; the others go at once without the rates, so the
    # reminders and lesson alerts of the next tick wait one timeout, not one per digest.
    asked: list[str] = []

    def hang(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        raise httpx.ReadTimeout("no answer", request=request)

    cbr = CbrClient(httpx.AsyncClient(transport=httpx.MockTransport(hang)))
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, clock=lambda: NOW)
    for user_id in (1, 2, 3):
        await make_user(id=user_id)
    assert await scheduler.send_digests(AT_0800) == 3
    assert asked == ["/daily_json.js"]


class OneForecast(StubMeteo):
    """One forecast, then failures: the kept forecast went stale and Open-Meteo is down."""

    async def forecast(self, lat: float, lon: float, **options: Any) -> dict[str, Any]:
        data = await super().forecast(lat, lon, **options)
        self.fail = True
        return data


async def test_the_weather_lost_before_the_day_is_read_still_waits(
    bot, sessionmaker, session, make_user, fake, cbr
) -> None:
    scheduler = Scheduler(bot, sessionmaker, OneForecast(), cbr, clock=lambda: NOW)
    user = await make_user()
    assert await scheduler.send_digests(AT_0800) == 0
    assert fake.calls == [] and (await reload(session, user)).last_morning_date is None
    assert await scheduler.send_digests(AT_0800 + timedelta(minutes=10)) == 1
    assert fake.sent_texts()[0].split("\n")[3] == UNAVAILABLE


async def test_digest_skips_disabled_blocked_and_out_of_window(
    scheduler, session, make_user, fake
) -> None:
    await make_user(id=1, morning_time="23:30", morning_enabled=False)
    await make_user(id=2, morning_time="23:30", bot_blocked=True)
    await make_user(id=3, morning_time="08:00")
    assert await scheduler.send_digests(AT_2345) == 0
    assert fake.calls == []


async def test_digest_403_blocks_user(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: user is deactivated")
    )
    await scheduler.send_digests(AT_2345)
    user = await reload(session, user)
    assert user.bot_blocked and user.last_morning_date is None


async def test_digest_bad_request_sets_last_morning_date_without_retry(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="23:30")
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    assert await scheduler.send_digests(AT_2345) == 0
    user = await reload(session, user)
    assert user.last_morning_date == date(2026, 9, 28)
    assert not user.bot_blocked
    assert await scheduler.send_digests(AT_0015) == 0
    assert len(fake.calls) == 1


async def test_digest_one_user_raising_does_not_stop_others(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(id=1, morning_time="23:30")
    await make_user(id=2, morning_time="23:30")
    original = Scheduler._digest

    async def flaky(self, user_id, day, now):
        if user_id == 1:
            raise RuntimeError("boom")
        return await original(self, user_id, day, now)

    monkeypatch.setattr(Scheduler, "_digest", flaky)
    assert await scheduler.send_digests(AT_2345) == 1
    assert len(fake.calls) == 1


async def test_tick_survives_a_failing_job(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    await make_user(morning_time="15:00")

    async def broken(*args, **kwargs):
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(reminders, "due", broken)
    await scheduler.tick()
    assert fake.sent_texts()[0].startswith("☀️ Доброе утро")


async def test_cleanup_removes_only_old_dialogs(scheduler, session) -> None:
    session.add_all(
        [
            FsmState(
                chat_id=1,
                user_id=1,
                state="NoteForm:text",
                data={},
                updated_at=NOW - timedelta(hours=25),
            ),
            FsmState(
                chat_id=2,
                user_id=2,
                state="NoteForm:text",
                data={},
                updated_at=NOW - timedelta(hours=1),
            ),
        ]
    )
    await session.commit()
    assert await scheduler.cleanup(NOW) == 1
    assert [row.chat_id for row in (await session.scalars(select(FsmState))).all()] == [2]


async def test_cleanup_drops_expired_share_cards(scheduler, session, make_user) -> None:
    user = await make_user()
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 9, 28))
    session.add(habit)
    await session.flush()
    session.add_all(
        [
            ShareCard(
                token="a" * 43,
                user_id=user.id,
                habit_id=habit.id,
                image=b"old",
                expires_at=NOW - timedelta(seconds=1),
            ),
            ShareCard(
                token="b" * 43,
                user_id=user.id,
                habit_id=habit.id,
                image=b"new",
                expires_at=NOW + timedelta(hours=1),
            ),
        ]
    )
    await session.commit()
    assert await scheduler.cleanup(NOW) == 1
    assert [card.token for card in (await session.scalars(select(ShareCard))).all()] == ["b" * 43]


async def test_cleanup_forgets_finished_reminders_nothing_can_reach(
    scheduler, session, make_user
) -> None:
    await make_user(morning_enabled=False)
    month_ago = NOW - timedelta(days=30)

    def row(text: str, status: ReminderStatus, sent_at: datetime | None = None) -> Reminder:
        return Reminder(
            user_id=1,
            text=text,
            status=status,
            due_at=month_ago,
            next_attempt_at=month_ago,
            sent_at=sent_at,
        )

    session.add_all(
        [
            row("cancelled", ReminderStatus.CANCELLED),
            row("done", ReminderStatus.DONE),
            row("failed", ReminderStatus.FAILED),
            row("sent", ReminderStatus.SENT, NOW - timedelta(days=7, minutes=1)),
            row("sent this week", ReminderStatus.SENT, NOW - timedelta(days=6)),
            row("done this week", ReminderStatus.DONE, NOW - timedelta(days=1)),
            # Pending stays however long ago it last fired: a monthly series, say.
            row("pending", ReminderStatus.PENDING, month_ago),
        ]
    )
    await session.commit()
    assert await scheduler.cleanup(NOW) == 4
    left = (await session.scalars(select(Reminder.text).order_by(Reminder.id))).all()
    assert left == ["sent this week", "done this week", "pending"]


async def test_a_snoozed_copy_outlives_its_forgotten_series(scheduler, session, make_user) -> None:
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(days=8))
    series.status, series.sent_at = ReminderStatus.CANCELLED, NOW - timedelta(days=8)
    later = NOW + timedelta(minutes=10)
    copy = Reminder(
        user_id=1, text="таблетки", due_at=later, next_attempt_at=later, parent_id=series.id
    )
    session.add(copy)
    await session.commit()
    assert await scheduler.cleanup(NOW) == 1
    assert (await session.scalars(select(Reminder.id))).all() == [copy.id]
    copy = await reload(session, copy)
    assert (copy.status, copy.parent_id) == (ReminderStatus.PENDING, None)


async def test_english_reminder(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False, language="en")
    await add_reminder(session, ago=timedelta(minutes=30), text="call mom")
    await scheduler.deliver_reminders(NOW)
    assert fake.sent_texts() == ["⏰ Reminder: call mom (was due at 14:30)"]


async def test_digest_user_with_a_broken_zone_does_not_stop_others(
    scheduler, session, make_user, fake
) -> None:
    await make_user(id=1, morning_time="23:30", tz="Mars/Olympus")
    await make_user(id=2, morning_time="23:30")
    assert await scheduler.send_digests(AT_2345) == 1
    assert [call.chat_id for call in fake.of(SendMessage)] == [2]


async def test_stop_ends_run_without_waiting_for_the_interval(
    bot, sessionmaker, meteo, cbr, make_user
) -> None:
    await make_user(morning_enabled=False)
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: NOW)
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.05)  # the first tick runs, then the scheduler sleeps
    scheduler.stop()
    await asyncio.wait_for(task, 1)  # returns by itself: nothing was cancelled
    assert task.done() and not task.cancelled()


async def test_stop_lets_the_current_tick_finish(
    bot, sessionmaker, meteo, cbr, monkeypatch
) -> None:
    scheduler = Scheduler(bot, sessionmaker, meteo, cbr, interval=3600, clock=lambda: NOW)
    started, finished = asyncio.Event(), []

    async def slow_tick() -> None:
        started.set()
        await asyncio.sleep(0.05)
        finished.append(True)

    monkeypatch.setattr(scheduler, "tick", slow_tick)
    task = asyncio.create_task(scheduler.run())
    await started.wait()
    scheduler.stop()  # in the middle of a tick
    await asyncio.wait_for(task, 1)
    assert finished == [True]


async def add_daily(session, *, time_local: str, occurrence: datetime, text: str = "таблетки"):
    reminder = Reminder(
        user_id=1,
        text=text,
        due_at=occurrence,
        next_attempt_at=occurrence,
        occurrence_at=occurrence,
        repeat=Repeat.DAILY,
        time_local=time_local,
        anchor_date=date(2026, 9, 1),
    )
    session.add(reminder)
    await session.commit()
    return reminder


async def test_fired_message_has_buttons(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    reminder = await add_reminder(session)
    await scheduler.deliver_reminders(NOW)
    markup = fake.of(SendMessage)[-1].reply_markup
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [b.text for b in buttons] == ["+10 мин", "+1 ч", "Завтра", "✓ Готово"]
    first = FireCb.unpack(buttons[0].callback_data)
    assert (first.action, first.id) == ("10m", reminder.id)
    assert first.at == int(reminder.due_at.timestamp() // 60)


async def test_repeat_moves_to_the_next_firing(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: таблетки"]
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING and series.sent_at == NOW
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_catches_up_with_one_message(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    three_days_ago = datetime(2026, 9, 25, 6, 0, tzinfo=UTC)  # 09:00 Moscow
    series = await add_daily(session, time_local="09:00", occurrence=three_days_ago)
    assert await scheduler.deliver_reminders(NOW) == 1
    assert fake.sent_texts() == ["⏰ Напоминание: таблетки (было на 09:00)"]
    series = await reload(session, series)
    assert series.due_at == datetime(2026, 9, 29, 6, 0, tzinfo=UTC)
    assert await scheduler.deliver_reminders(NOW + timedelta(minutes=1)) == 0


async def test_blocked_user_keeps_the_series(scheduler, session, make_user, fake) -> None:
    user = await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    fake.errors.append(
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user")
    )
    await scheduler.deliver_reminders(NOW)
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)
    assert (await reload(session, user)).bot_blocked


async def test_bad_request_moves_a_series_on(scheduler, session, make_user, fake) -> None:
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    fake.errors.append(TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"))
    await scheduler.deliver_reminders(NOW)
    series = await reload(session, series)
    assert series.status == ReminderStatus.PENDING
    assert series.last_error == "Bad Request: chat not found"
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_survives_max_temporary_failures(scheduler, session, make_user, fake) -> None:
    """Exhausting every backoff attempt with a temporary error still moves the series on,
    never fails it — this pins `tz=user.timezone` on the temporary-failure `schedule_retry`
    call inside `deliver_reminders`."""
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))
    moment = NOW
    for _ in range(reminders.MAX_FAILURES):
        fake.errors.append(TelegramServerError(method=METHOD, message="Bad Gateway"))
        await scheduler.deliver_reminders(moment)
        series = await reload(session, series)
        moment = series.next_attempt_at
    assert series.status == ReminderStatus.PENDING
    assert series.attempts == 0
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_repeat_survives_an_unexpected_rendering_error(
    scheduler, session, make_user, fake, monkeypatch
) -> None:
    """Same as above, but through the `except Exception` path (e.g. a formatting bug) —
    pins `tz=user.timezone` on that call site's `schedule_retry` too."""
    await make_user(morning_enabled=False)
    series = await add_daily(session, time_local="14:59", occurrence=NOW - timedelta(minutes=1))

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "reminder_text", broken)
    moment = NOW
    for _ in range(reminders.MAX_FAILURES):
        await scheduler.deliver_reminders(moment)
        series = await reload(session, series)
        moment = series.next_attempt_at
    assert series.status == ReminderStatus.PENDING
    assert series.attempts == 0
    assert series.due_at == datetime(2026, 9, 29, 11, 59, tzinfo=UTC)


async def test_the_digest_lists_todays_firing_of_a_repeat(
    scheduler, session, make_user, fake
) -> None:
    user = await make_user(morning_time="08:00")
    at_0800 = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)
    rule = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 9, 28))
    await reminders.create_repeating(session, user, "таблетки", rule, at_0800)
    await session.commit()
    assert await scheduler.send_digests(at_0800) == 1
    assert "• 21:00 — таблетки" in fake.sent_texts()[0]
