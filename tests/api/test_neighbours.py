"""What one user keeps never reaches another user's lists, counts and limits.

User 2, the neighbour, has everything another user could stumble on: the timetable of the MIREA
group 4805 with its week labels and lesson alerts, 20 pending reminders (one due tonight, one a
daily repeat), 50 notes with 5 of them pinned, and money entries at the money limits (made small
here, as tests/unit/test_money.py does). User 1 asks: none of it shows, counts or changes for them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from assistant.core.config import LIMITS
from assistant.core.models import Repeat, User
from assistant.core.money_style import EXPENSE
from assistant.core.services import groups, money, notes, reminders
from assistant.core.services.group_names import GroupHeader
from assistant.core.services.recurrence import Rule
from tests.api.conftest import NOW

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
MIREA = (FIXTURES / "mirea_ikbo_63_24.ics").read_bytes()
WEEK = "/api/agenda?from=2026-09-28&to=2026-10-04"
NEW_YORK = {"name": "Нью-Йорк", "lat": 40.71, "lon": -74.0, "timezone": "America/New_York"}


@pytest.fixture
async def neighbour(client, auth, session, calendars, monkeypatch) -> None:
    await groups.remember(session, 4805, GroupHeader("ИКБО-63-24", date(2026, 12, 31)), NOW)
    await session.commit()
    calendars.bodies[groups.calendar_url(4805)] = MIREA
    connected = await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth(2))
    assert connected.status_code == 200
    alerts = {"lesson_reminder_minutes": 30}
    assert (await client.patch("/api/schedule", json=alerts, headers=auth(2))).status_code == 200
    user = await session.get(User, 2)
    assert user is not None
    await reminders.create(session, user, "врач в 19:30", datetime(2026, 9, 28, 19, 30), NOW)
    daily = Rule(repeat=Repeat.DAILY, time_local="07:30", anchor_date=date(2026, 9, 28))
    await reminders.create_repeating(session, user, "зарядка", daily, NOW)
    for day in range(LIMITS.reminders - 2):
        await reminders.create(session, user, f"дело {day}", datetime(2026, 10, 5 + day, 10), NOW)
    for number in range(LIMITS.notes):
        pinned = number < LIMITS.pinned_notes
        await notes.create(session, 2, f"заметка {number}", pinned=pinned, now=NOW)
    monkeypatch.setattr(money, "LIMITS", replace(LIMITS, money_entries=2, money_entries_month=1))
    cafe = (await money.categories(session, user, kind=EXPENSE))[0]
    await money.add_entry(session, user, amount=25_000, category_id=cafe.id, now=NOW)
    august = date(2026, 8, 31)
    await money.add_entry(session, user, amount=9_900, category_id=cafe.id, day=august, now=NOW)
    await session.commit()


@pytest.mark.usefixtures("neighbour")
async def test_my_day_and_calendar_show_none_of_the_neighbours(client, auth) -> None:
    week = (await client.get(WEEK, headers=auth())).json()["days"]
    assert [(day["label"], day["items"]) for day in week] == [(None, [])] * 7
    today = (await client.get("/api/today", headers=auth())).json()
    assert today["reminders_today"] == []
    assert (today["notes_count"], today["pinned_notes"]) == (0, [])
    assert (today["has_schedule"], today["lessons"], today["week_label"]) == (False, [], None)
    assert (today["money"]["count"], today["money"]["spent"], today["money"]["today"]) == (0, 0, 0)
    month = (await client.get("/api/money", headers=auth())).json()
    assert (month["entries"], month["spent"], month["first_month"]) == ([], 0, None)


@pytest.mark.usefixtures("neighbour")
async def test_the_neighbours_limits_are_not_mine(client, auth) -> None:
    me = auth()
    for note in ({"text": "моя"}, {"text": "важная", "pinned": True}):
        assert (await client.post("/api/notes", json=note, headers=me)).status_code == 201
    reminder = {"text": "позвонить", "due_local": "2026-09-29T10:00"}
    assert (await client.post("/api/reminders", json=reminder, headers=me)).status_code == 201
    budget = await client.put("/api/money/budget", json={"amount": "300"}, headers=me)
    assert budget.status_code == 200
    categories = (await client.get("/api/money/categories", headers=me)).json()
    cafe = next(item["id"] for item in categories if item["kind"] == "expense")
    saved = await client.post(
        "/api/money/entries", json={"amount": "10", "category_id": cafe}, headers=me
    )
    # Room under the limits the neighbour has filled, and 10 of my 300 warn of nothing.
    assert (saved.status_code, saved.json()["alerts"]) == (201, [])


@pytest.mark.usefixtures("neighbour")
async def test_a_classmates_refresh_and_disconnect_leave_my_timetable(client, auth, clock) -> None:
    me = auth()
    mine = (await client.put("/api/schedule", json={"mirea_id": 4805}, headers=me)).json()
    assert mine["source"]["lessons_ahead"] == 36  # mine alone, not the group's twice
    week = (await client.get(WEEK, headers=me)).json()
    assert {day["label"] for day in week["days"]} == {"5 неделя"}
    clock[0] = NOW + timedelta(minutes=2)
    assert (await client.post("/api/schedule/refresh", headers=auth(2))).status_code == 200
    assert (await client.get("/api/schedule", headers=me)).json() == mine
    assert (await client.get(WEEK, headers=me)).json() == week
    assert (await client.delete("/api/schedule", headers=auth(2))).status_code == 204
    assert (await client.get("/api/schedule", headers=me)).json() == mine
    assert (await client.get(WEEK, headers=me)).json() == week


@pytest.mark.usefixtures("neighbour")
async def test_my_move_leaves_the_neighbours_repeats_alone(client, auth) -> None:
    theirs = (await client.get("/api/reminders", headers=auth(2))).json()
    assert (await client.put("/api/me/city", json=NEW_YORK, headers=auth())).status_code == 200
    assert (await client.get("/api/reminders", headers=auth(2))).json() == theirs
