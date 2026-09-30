from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import phrases, reminders, users
from assistant.core.services.recurrence import WEEKDAYS, Rule

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # Monday, 15:00 in Moscow
LOCAL_NOW = datetime(2026, 9, 28, 15, 0)
DAILY_21 = Rule(repeat=Repeat.DAILY, time_local="21:00", anchor_date=date(2026, 9, 28))


def utc(y, m, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=UTC)


async def test_create_repeating_schedules_the_next_firing(session, make_user) -> None:
    user = await make_user()
    reminder = await reminders.create_repeating(session, user, " таблетки ", DAILY_21, NOW)
    assert reminder.text == "таблетки" and reminder.repeat is Repeat.DAILY
    assert reminder.occurrence_at == reminder.due_at == utc(2026, 9, 28, 18)
    assert reminder.next_attempt_at == utc(2026, 9, 28, 18)
    assert reminders.rule_of(reminder) == DAILY_21


async def test_create_repeating_validates_and_counts(session, make_user) -> None:
    user = await make_user()
    bad = Rule(repeat=Repeat.WEEKLY, time_local="09:00", anchor_date=date(2026, 9, 28))
    with pytest.raises(InvalidInput):
        await reminders.create_repeating(session, user, "x", bad, NOW)
    for i in range(20):
        await reminders.create(session, user, f"r{i}", datetime(2099, 1, 1, 10), NOW)
    with pytest.raises(LimitReached):
        await reminders.create_repeating(session, user, "x", DAILY_21, NOW)


@pytest.mark.parametrize(
    ("message", "repeat", "due"),
    [
        ("завтра в 9 купить молоко", Repeat.NONE, datetime(2026, 9, 29, 6, tzinfo=UTC)),
        ("по будням в 7:30 зарядка", Repeat.WEEKLY, datetime(2026, 9, 29, 4, 30, tzinfo=UTC)),
    ],
)
async def test_create_from_a_phrase(session, make_user, message, repeat, due) -> None:
    user = await make_user()
    parsed = phrases.parse(message, LOCAL_NOW)
    reminder = await reminders.create_from(session, user, parsed, NOW)
    assert (reminder.repeat, reminder.due_at) == (repeat, due)


async def test_create_from_needs_a_time_and_a_text(session, make_user) -> None:
    user = await make_user()
    no_time = phrases.parse("завтра позвонить", LOCAL_NOW)
    with pytest.raises(InvalidInput) as error:
        await reminders.create_from(session, user, no_time, NOW)
    assert error.value.params["reason"] == "needs_time"
    no_text = phrases.parse("завтра в 9", LOCAL_NOW)
    with pytest.raises(InvalidInput) as error:
        await reminders.create_from(session, user, no_text, NOW)
    assert error.value.params["field"] == "text"


async def test_update_text_time_and_repeat(session, make_user) -> None:
    user = await make_user()
    reminder = await reminders.create(session, user, "a", datetime(2026, 9, 29, 9), NOW)
    await reminders.update_reminder(session, user, reminder.id, text="b", rule=DAILY_21, now=NOW)
    assert (reminder.text, reminder.repeat) == ("b", Repeat.DAILY)
    assert reminder.due_at == utc(2026, 9, 28, 18)
    await reminders.update_reminder(
        session, user, reminder.id, when_local=datetime(2026, 10, 1, 10), now=NOW
    )
    assert reminder.repeat is Repeat.NONE and reminder.time_local is None
    assert reminder.due_at == reminder.occurrence_at == utc(2026, 10, 1, 7)
    with pytest.raises(InvalidInput) as error:
        await reminders.update_reminder(
            session, user, reminder.id, when_local=datetime(2026, 9, 28, 10), now=NOW
        )
    assert error.value.params["reason"] == "past"


async def test_update_refuses_foreign_and_finished(session, make_user) -> None:
    user = await make_user()
    other = await make_user(id=2)
    reminder = await reminders.create(session, user, "a", datetime(2026, 9, 29, 9), NOW)
    with pytest.raises(NotFound):
        await reminders.update_reminder(session, other, reminder.id, text="x", now=NOW)
    await reminders.cancel(session, user.id, reminder.id)
    with pytest.raises(NotFound):
        await reminders.update_reminder(session, user, reminder.id, text="x", now=NOW)


def test_snooze_until() -> None:
    fired = utc(2026, 9, 28, 18)  # 21:00 Moscow
    tz = "Europe/Moscow"
    assert reminders.snooze_until("10m", fired, tz, NOW) == NOW + timedelta(minutes=10)
    assert reminders.snooze_until("1h", fired, tz, NOW) == NOW + timedelta(hours=1)
    # «Завтра» = the same local time as the firing, on the next local day
    assert reminders.snooze_until("tomorrow", fired, tz, NOW) == utc(2026, 9, 29, 18)


async def test_snooze_moves_a_one_off(session, make_user) -> None:
    user = await make_user()
    reminder = await reminders.create(session, user, "a", datetime(2026, 9, 28, 16), NOW)
    reminders.mark_sent(reminder, NOW)
    until = NOW + timedelta(minutes=10)
    moved = await reminders.snooze(session, user, reminder.id, until, NOW)
    assert moved is reminder and reminder.status is ReminderStatus.PENDING
    assert reminder.due_at == reminder.next_attempt_at == until


async def test_snoozing_a_repeat_makes_a_copy(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    copy = await reminders.snooze(session, user, series.id, NOW + timedelta(hours=1), NOW)
    assert copy.id != series.id and copy.parent_id == series.id
    assert copy.repeat is Repeat.NONE and copy.text == "таблетки"
    assert series.due_at == utc(2026, 9, 28, 18)  # the series goes on untouched
    with pytest.raises(InvalidInput):
        await reminders.snooze(session, user, series.id, NOW - timedelta(minutes=1), NOW)


async def test_done(session, make_user) -> None:
    user = await make_user()
    one_off = await reminders.create(session, user, "a", datetime(2026, 9, 28, 16), NOW)
    series = await reminders.create_repeating(session, user, "b", DAILY_21, NOW)
    assert await reminders.done(session, user.id, one_off.id)
    assert one_off.status is ReminderStatus.DONE
    assert await reminders.done(session, user.id, series.id)
    assert series.status is ReminderStatus.PENDING  # a repeat keeps going
    assert not await reminders.done(session, 2, series.id)


async def test_mark_delivered_and_give_up(session, make_user) -> None:
    user = await make_user()
    tz = "Europe/Moscow"
    one_off = await reminders.create(session, user, "a", datetime(2026, 9, 28, 16), NOW)
    series = await reminders.create_repeating(session, user, "b", DAILY_21, NOW)
    later = utc(2026, 9, 28, 18, 0, 5)
    reminders.mark_delivered(one_off, later, tz)
    reminders.mark_delivered(series, later, tz)
    assert one_off.status is ReminderStatus.SENT
    assert series.status is ReminderStatus.PENDING and series.sent_at == later
    assert series.due_at == utc(2026, 9, 29, 18) and series.attempts == 0
    reminders.give_up(series, "Forbidden", later, tz)
    assert series.status is ReminderStatus.PENDING and series.last_error == "Forbidden"
    other = await reminders.create(session, user, "c", datetime(2026, 9, 28, 17), NOW)
    reminders.give_up(other, "Bad Request", later, tz)
    assert other.status is ReminderStatus.FAILED


async def test_retry_budget_never_kills_a_series(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "b", DAILY_21, NOW)
    moment = utc(2026, 9, 28, 18)
    for _ in range(reminders.MAX_FAILURES):
        reminders.schedule_retry(series, moment, "network", tz="Europe/Moscow")
    assert series.status is ReminderStatus.PENDING
    assert series.due_at == utc(2026, 9, 29, 18) and series.attempts == 0


async def test_shown_at_reports_the_latest_missed_firing(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "b", DAILY_21, NOW)
    three_days_later = utc(2026, 10, 1, 12)
    assert reminders.shown_at(series, "Europe/Moscow", three_days_later) == utc(2026, 9, 30, 18)


async def test_expire_stale_fails_one_offs_and_moves_repeats(session, make_user) -> None:
    user = await make_user()
    one_off = await reminders.create(session, user, "a", datetime(2026, 9, 28, 16), NOW)
    series = await reminders.create_repeating(session, user, "b", DAILY_21, NOW)
    much_later = utc(2026, 10, 5, 12)
    assert await reminders.expire_stale(session, user.id, much_later, "Europe/Moscow") == 2
    await session.refresh(one_off)
    assert one_off.status is ReminderStatus.FAILED
    assert series.status is ReminderStatus.PENDING and series.due_at == utc(2026, 10, 5, 18)


async def test_moving_keeps_local_time_of_repeats(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    one_off = await reminders.create(session, user, "врач", datetime(2026, 9, 29, 10), NOW)
    await users.set_city(session, user, "Берлин", 52.52, 13.4, "Europe/Berlin", now=NOW)
    assert series.due_at == utc(2026, 9, 28, 19)  # 21:00 in Berlin (summer time, UTC+2)
    assert one_off.due_at == utc(2026, 9, 29, 7)  # the same moment as before


async def test_between_lists_one_offs_and_firings(session, make_user) -> None:
    user = await make_user()
    week = Rule(
        repeat=Repeat.WEEKLY, time_local="07:30", anchor_date=date(2026, 9, 28), weekdays=WEEKDAYS
    )
    await reminders.create_repeating(session, user, "зарядка", week, NOW)
    await reminders.create(session, user, "врач", datetime(2026, 9, 29, 10), NOW)
    found = await reminders.between(session, user, utc(2026, 9, 29), utc(2026, 9, 30, 21))
    assert [(r.text, m) for r, m in found] == [
        ("зарядка", utc(2026, 9, 29, 4, 30)),
        ("врач", utc(2026, 9, 29, 7)),
        ("зарядка", utc(2026, 9, 30, 4, 30)),
    ]


async def test_app_requests_do_not_unblock_or_grant_writing(session, make_user) -> None:
    user = await make_user(bot_blocked=True, can_write=False)
    await users.ensure(session, user.id, "Test", "ru", NOW, from_bot=False)
    assert user.bot_blocked and not user.can_write
    await users.allow_write(session, user)
    assert user.can_write
    await users.ensure(session, user.id, "Test", "ru", NOW)  # a message to the bot
    assert not user.bot_blocked


async def test_only_the_bot_marks_new_users_writable(session) -> None:
    from_app = await users.ensure(session, 77, "New", "en", NOW, from_bot=False)
    assert from_app.can_write is False
    from_bot = await users.ensure(session, 78, "Bot", "en", NOW)
    assert from_bot.can_write is True


async def test_tomorrow_on_a_daily_repeat_does_not_duplicate(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    delivered = utc(2026, 9, 28, 18, 0, 5)
    reminders.mark_delivered(series, delivered, user.timezone)
    until = reminders.snooze_until("tomorrow", utc(2026, 9, 28, 18), user.timezone, delivered)
    assert until == series.due_at == utc(2026, 9, 29, 18)
    result = await reminders.snooze(session, user, series.id, until, delivered)
    assert result.id == series.id
    found = await reminders.between(session, user, utc(2026, 9, 29), utc(2026, 9, 30))
    assert [(r.id, m) for r, m in found] == [(series.id, utc(2026, 9, 29, 18))]


async def test_ten_minutes_on_a_repeat_makes_one_copy(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    delivered = utc(2026, 9, 28, 18, 0, 5)
    reminders.mark_delivered(series, delivered, user.timezone)
    until = reminders.snooze_until("10m", utc(2026, 9, 28, 18), user.timezone, delivered)
    copy = await reminders.snooze(session, user, series.id, until, delivered)
    assert copy.id != series.id and copy.parent_id == series.id
    # From just after the delivered firing (the calendar lists past firings of a day too).
    found = await reminders.between(session, user, utc(2026, 9, 28, 18, 5), utc(2026, 9, 30))
    assert [(r.id, m) for r, m in found] == [
        (copy.id, utc(2026, 9, 28, 18, 10, 5)),
        (series.id, utc(2026, 9, 29, 18)),
    ]


async def test_double_tap_on_a_repeat_snooze_within_a_minute_returns_the_same_copy(
    session, make_user
) -> None:
    """Two presses of the same button a few seconds apart target slightly different `until`
    moments (both computed from the press time) — close enough still counts as the same
    snooze and shares one copy; a different kind still gets its own, distinct moment."""
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    fired = utc(2026, 9, 28, 18)
    t1 = utc(2026, 9, 28, 18, 0, 5)
    reminders.mark_delivered(series, t1, user.timezone)

    until1 = reminders.snooze_until("10m", fired, user.timezone, t1)
    first = await reminders.snooze(session, user, series.id, until1, t1)

    t2 = t1 + timedelta(seconds=2)
    until2 = reminders.snooze_until("10m", fired, user.timezone, t2)
    second = await reminders.snooze(session, user, series.id, until2, t2)
    assert second.id == first.id
    copies = (
        await session.scalars(
            select(Reminder).where(
                Reminder.parent_id == series.id, Reminder.status == ReminderStatus.PENDING
            )
        )
    ).all()
    assert len(copies) == 1

    until3 = reminders.snooze_until("1h", fired, user.timezone, t2)
    third = await reminders.snooze(session, user, series.id, until3, t2)
    assert third.id not in (first.id, series.id)
    copies = (
        await session.scalars(
            select(Reminder).where(
                Reminder.parent_id == series.id, Reminder.status == ReminderStatus.PENDING
            )
        )
    ).all()
    assert len(copies) == 2


async def test_snoozing_a_sent_one_off_respects_the_limit(session, make_user) -> None:
    user = await make_user()
    fired = await reminders.create(session, user, "врач", datetime(2026, 9, 28, 16), NOW)
    for i in range(19):
        await reminders.create(session, user, f"r{i}", datetime(2099, 1, 1, 10), NOW)
    reminders.mark_delivered(fired, utc(2026, 9, 28, 13), user.timezone)
    await reminders.create(session, user, "ещё", datetime(2099, 1, 1, 11), NOW)
    with pytest.raises(LimitReached):
        await reminders.snooze(session, user, fired.id, utc(2026, 9, 28, 14), utc(2026, 9, 28, 13))


async def test_done_and_foreign_reminders_cannot_be_snoozed(session, make_user) -> None:
    user = await make_user()
    other = await make_user(id=2)
    one_off = await reminders.create(session, user, "врач", datetime(2026, 9, 28, 16), NOW)
    assert await reminders.done(session, user.id, one_off.id)
    with pytest.raises(NotFound):
        await reminders.snooze(session, user, one_off.id, utc(2026, 9, 28, 14), NOW)
    theirs = await reminders.create(session, other, "чужое", datetime(2026, 9, 28, 16), NOW)
    with pytest.raises(NotFound):
        await reminders.snooze(session, user, theirs.id, utc(2026, 9, 28, 14), NOW)
    assert not await reminders.done(session, user.id, theirs.id)


async def test_a_repeat_created_after_its_time_starts_tomorrow(session, make_user) -> None:
    user = await make_user()
    parsed = phrases.parse("каждый день в 9 таблетки", LOCAL_NOW)
    assert parsed is not None
    series = await reminders.create_from(session, user, parsed, NOW)
    assert series.due_at == utc(2026, 9, 29, 6)
    assert series.anchor_date == date(2026, 9, 29)
    assert await reminders.between(session, user, utc(2026, 9, 27, 21), utc(2026, 9, 28, 21)) == []


async def test_moving_west_right_after_a_firing_does_not_fire_again(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    reminders.mark_delivered(series, utc(2026, 9, 28, 18, 0, 5), user.timezone)
    later = utc(2026, 9, 28, 18, 30)
    await users.set_city(session, user, "Лондон", 51.5, -0.12, "Europe/London", now=later)
    assert series.due_at == utc(2026, 9, 29, 20)  # Tuesday 21:00 in London, not Monday


async def test_moving_east_past_the_time_fires_now(session, make_user) -> None:
    user = await make_user()
    await users.set_city(session, user, "Лондон", 51.5, -0.12, "Europe/London", now=NOW)
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    assert series.due_at == utc(2026, 9, 28, 20)  # 21:00 in London (UTC+1)
    later = utc(2026, 9, 28, 18, 30)  # 21:30 in Moscow, 19:30 in London
    await users.set_city(session, user, "Москва", 55.75, 37.62, "Europe/Moscow", now=later)
    assert series.due_at == later


async def test_setting_the_same_city_changes_nothing(session, make_user) -> None:
    user = await make_user()
    series = await reminders.create_repeating(session, user, "таблетки", DAILY_21, NOW)
    series.attempts = 2
    await users.set_city(session, user, "Москва", 55.75, 37.62, "Europe/Moscow", now=NOW)
    assert series.attempts == 2 and series.due_at == utc(2026, 9, 28, 18)


async def test_biweekly_from_today_starts_at_the_first_matching_day(session, make_user) -> None:
    user = await make_user()
    rule = Rule(
        repeat=Repeat.WEEKLY,
        time_local="10:00",
        anchor_date=date(2026, 9, 28),
        weekdays=1,
        interval_weeks=2,
    )
    reminder = await reminders.create_repeating(session, user, "уборка", rule, NOW)
    # 07:30 today already passed; the very next Monday (not the "off" week's twin two weeks
    # later) is the first firing, and it becomes the new anchor (Task 8 fix round 1).
    assert reminder.due_at == utc(2026, 10, 5, 7)
    assert reminder.anchor_date == date(2026, 10, 5)


async def test_editing_a_biweekly_series_keeps_its_weeks(session, make_user) -> None:
    user = await make_user()
    rule = Rule(
        repeat=Repeat.WEEKLY,
        time_local="10:00",
        anchor_date=date(2026, 10, 5),
        weekdays=1,
        interval_weeks=2,
    )
    series = await reminders.create_repeating(session, user, "уборка", rule, NOW)
    assert series.anchor_date == date(2026, 10, 5)
    edited_rule = Rule(
        repeat=Repeat.WEEKLY,
        time_local="12:00",
        anchor_date=date(2026, 10, 5),
        weekdays=1,
        interval_weeks=2,
    )
    later = utc(2026, 10, 20, 12)
    edited = await reminders.update_reminder(session, user, series.id, rule=edited_rule, now=later)
    # 2026-10-19 (Monday) is an "off" week for this anchor; the next "on" Monday is 2026-11-02.
    assert edited.due_at == utc(2026, 11, 2, 9)
    # The stored anchor still advances to the first real firing (Task 5), but Nov 2 is exactly
    # two intervals (28 days) after Oct 5, so the series' on/off week parity is unchanged.
    assert edited.anchor_date == date(2026, 11, 2)


async def test_a_failed_edit_leaves_the_reminder_untouched(session, make_user) -> None:
    user = await make_user()
    one_off = await reminders.create(session, user, "врач", datetime(2026, 9, 29, 10), NOW)
    with pytest.raises(InvalidInput):
        await reminders.update_reminder(
            session, user, one_off.id, text="новое", when_local=datetime(2026, 9, 28, 10), now=NOW
        )
    assert one_off.text == "врач" and one_off.due_at == utc(2026, 9, 29, 7)


async def test_a_text_only_edit_keeps_a_snoozed_moment_to_the_second(session, make_user) -> None:
    user = await make_user()
    one_off = await reminders.create(session, user, "чай", datetime(2026, 9, 28, 16), NOW)
    until = NOW + timedelta(minutes=10, seconds=37)  # «+10 мин» keeps the press's seconds
    await reminders.snooze(session, user, one_off.id, until, NOW)
    later = NOW + timedelta(hours=1)  # overdue by now; the form shows and sends 15:10
    await reminders.update_reminder(
        session,
        user,
        one_off.id,
        text="зелёный чай",
        when_local=datetime(2026, 9, 28, 15, 10),
        now=later,
    )
    assert (one_off.text, one_off.due_at) == ("зелёный чай", until)
