from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from assistant.core.services import groups
from assistant.core.services.group_names import GroupHeader
from tests.api.conftest import NOW

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
MIREA = (FIXTURES / "mirea_ikbo_63_24.ics").read_bytes()
OUTLOOK = (FIXTURES / "outlook.ics").read_bytes()
GROUP_URL = groups.calendar_url(4805)
LINK = "https://uni.example/t.ics"


@pytest.fixture
async def ready(session, calendars, monkeypatch):
    """The MIREA group is in the directory and every calendar can be downloaded."""
    monkeypatch.setattr(groups, "PRUNE_MIN_FOUND", 2)  # two groups count as a built directory
    await groups.remember(session, 4805, GroupHeader("ИКБО-63-24", date(2026, 12, 31)), NOW)
    await groups.remember(session, 4804, GroupHeader("ИКБО-62-24", date(2026, 12, 31)), NOW)
    await groups.record_run(session, groups.FULL_JOB, NOW, "checked 6000, found 2")
    await session.commit()
    calendars.bodies[GROUP_URL] = MIREA
    calendars.bodies[LINK] = (FIXTURES / "foreign.ics").read_bytes()
    calendars.bodies["https://uni.example/login"] = b"<!DOCTYPE html><html>Login</html>"
    return calendars


def problem(response) -> tuple[int, str | None, str | None]:
    body = response.json()
    return response.status_code, body.get("field"), body.get("reason")


async def test_nothing_is_connected_at_first(client, auth) -> None:
    response = await client.get("/api/schedule", headers=auth())
    assert response.status_code == 200 and response.json() == {"source": None}


async def test_group_search(client, auth, ready) -> None:
    found = await client.get("/api/schedule/groups", params={"q": "ikbo-63"}, headers=auth())
    assert found.json() == {"groups": [{"id": 4805, "name": "ИКБО-63-24"}], "building": False}
    both = await client.get("/api/schedule/groups", params={"q": "ИКБО"}, headers=auth())
    assert [group["name"] for group in both.json()["groups"]] == ["ИКБО-62-24", "ИКБО-63-24"]
    nothing = await client.get("/api/schedule/groups", headers=auth())
    assert nothing.json() == {"groups": [], "building": False}


async def test_group_search_while_the_directory_is_built(client, auth, session) -> None:
    await groups.remember(session, 4804, GroupHeader("ИКБО-62-24", date(2026, 12, 31)), NOW)
    await session.commit()
    found = await client.get("/api/schedule/groups", params={"q": "ИКБО"}, headers=auth())
    assert found.json() == {"groups": [{"id": 4804, "name": "ИКБО-62-24"}], "building": True}


async def test_connect_a_group(client, auth, ready) -> None:
    response = await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    assert response.status_code == 200
    assert response.json() == {
        "source": {
            "kind": "mirea",
            "title": "ИКБО-63-24",
            "mirea_id": 4805,
            "url": GROUP_URL,
            "fetched_at": "2026-09-28T12:00:00Z",
            "ok_at": "2026-09-28T12:00:00Z",
            "error": None,
            "stale": False,
            "lesson_reminder_minutes": None,
            "lessons_ahead": 36,
        }
    }
    assert (await client.get("/api/schedule", headers=auth())).json() == response.json()


async def test_connect_a_link(client, auth, ready) -> None:
    response = await client.put(
        "/api/schedule", json={"url": "webcal://uni.example/t.ics"}, headers=auth()
    )
    source = response.json()["source"]
    assert (source["kind"], source["url"], source["title"]) == ("url", LINK, "Physics 101")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"url": "http://uni.example/t.ics"}, (422, "url", "forbidden_host")),
        ({"url": "https://uni.example/gone.ics"}, (422, "url", "unreachable")),
        ({"url": "https://uni.example/login"}, (422, "calendar", "not_calendar")),
        ({"mirea_id": 4805, "url": LINK}, (422, "schedule", "source")),
        ({}, (422, "schedule", "source")),
        ({"mirea_id": 4000}, (404, None, None)),
    ],
)
async def test_connecting_fails_clearly(client, auth, ready, body, expected) -> None:
    response = await client.put("/api/schedule", json=body, headers=auth())
    assert problem(response) == expected
    assert (await client.get("/api/schedule", headers=auth())).json() == {"source": None}


async def test_upload_a_file(client, auth) -> None:
    response = await client.post(
        "/api/schedule/file",
        params={"name": "Английский.ics"},
        content=OUTLOOK,
        headers={**auth(), "Content-Type": "text/calendar"},
    )
    assert response.status_code == 200
    source = response.json()["source"]
    assert (source["kind"], source["title"], source["url"]) == ("file", "Английский", None)
    assert source["lessons_ahead"] == 1


async def test_a_file_that_is_too_big_or_not_a_calendar(client, auth) -> None:
    big = await client.post(
        "/api/schedule/file", content=b"B" * (2 * 1024 * 1024 + 1), headers=auth()
    )
    assert problem(big) == (422, "file", "too_large")
    pdf = await client.post("/api/schedule/file", content=b"%PDF-1.7", headers=auth())
    assert problem(pdf) == (422, "calendar", "not_calendar")


async def test_refresh_at_most_once_a_minute(client, auth, ready, clock) -> None:
    assert (await client.post("/api/schedule/refresh", headers=auth())).status_code == 404
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    early = await client.post("/api/schedule/refresh", headers=auth())
    assert early.status_code == 429 and early.json()["code"] == "rate_limited"
    assert int(early.headers["Retry-After"]) == 60
    clock[0] = NOW + timedelta(minutes=2)
    response = await client.post("/api/schedule/refresh", headers=auth())
    assert response.status_code == 200
    assert response.json()["source"]["ok_at"] == "2026-09-28T12:02:00Z"


async def test_a_failed_refresh_reports_the_error_and_keeps_the_lessons(
    client, auth, ready, clock
) -> None:
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    ready.errors[GROUP_URL] = "unreachable"
    clock[0] = NOW + timedelta(days=4)
    fresh = auth(signed_at=clock[0])  # the Telegram sign-in is valid for a day
    source = (await client.post("/api/schedule/refresh", headers=fresh)).json()["source"]
    assert source["error"] == "unreachable" and source["stale"] is True
    assert source["ok_at"] == "2026-09-28T12:00:00Z" and source["lessons_ahead"] > 0


async def test_lesson_alerts(client, auth, ready) -> None:
    patch = await client.patch(
        "/api/schedule", json={"lesson_reminder_minutes": 15}, headers=auth()
    )
    assert patch.status_code == 404  # nothing connected yet
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    patch = await client.patch(
        "/api/schedule", json={"lesson_reminder_minutes": 15}, headers=auth()
    )
    assert patch.json()["source"]["lesson_reminder_minutes"] == 15
    wrong = await client.patch("/api/schedule", json={"lesson_reminder_minutes": 7}, headers=auth())
    assert problem(wrong)[0] == 422
    off = await client.patch(
        "/api/schedule", json={"lesson_reminder_minutes": None}, headers=auth()
    )
    assert off.json()["source"]["lesson_reminder_minutes"] is None


async def test_disconnect(client, auth, ready) -> None:
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    assert (await client.delete("/api/schedule", headers=auth())).status_code == 204
    assert (await client.delete("/api/schedule", headers=auth())).status_code == 404
    agenda = await client.get("/api/agenda?from=2026-09-28&to=2026-10-04", headers=auth())
    assert all(day["items"] == [] and day["label"] is None for day in agenda.json()["days"])


async def test_agenda_has_lessons_and_week_labels(client, auth, ready) -> None:
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    reminder = {"text": "сдать отчёт", "due_local": "2026-09-30T10:00"}
    assert (await client.post("/api/reminders", json=reminder, headers=auth())).status_code == 201
    days = (await client.get("/api/agenda?from=2026-09-28&to=2026-10-04", headers=auth())).json()
    by_date = {day["date"]: day for day in days["days"]}
    assert {day["label"] for day in days["days"]} == {"5 неделя"}
    wednesday = by_date["2026-09-30"]["items"]
    assert [item["kind"] for item in wednesday] == ["reminder", "lesson"]  # by time
    assert wednesday[1] == {
        "kind": "lesson",
        "time": "12:40",
        "end": "14:10",
        "title": "Разработка баз данных",
        "lesson_kind": "ПР",
        "room": "И-212-б (В-78)",
    }
    assert by_date["2026-09-28"]["items"] == []


async def test_agenda_shows_lessons_in_the_users_zone(client, auth, ready) -> None:
    await client.put(
        "/api/me/city",
        json={"name": "Гонолулу", "lat": 21.3, "lon": -157.86, "timezone": "Pacific/Honolulu"},
        headers=auth(),
    )
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    days = (await client.get("/api/agenda?from=2026-09-28&to=2026-10-04", headers=auth())).json()
    items = {
        day["date"]: [(item["time"], item["title"]) for item in day["items"]]
        for day in days["days"]
    }
    # Moscow is 13 hours ahead: Wednesday 12:40 there is Tuesday 23:40 here, Thursday 09:00
    # is Wednesday 20:00, Friday 09:00 is Thursday 20:00.
    assert items["2026-09-29"] == [("23:40", "Разработка баз данных")]
    assert items["2026-09-30"] == [("20:00", "Военная кафедра")]
    assert items["2026-10-01"] == [
        ("20:00", "Проектирование и разработка мобильных приложений на языке Котлин")
    ]


async def test_today_lists_the_lessons(client, auth, ready, clock) -> None:
    body = (await client.get("/api/today", headers=auth())).json()
    assert (body["has_schedule"], body["lessons"], body["week_label"]) == (False, [], None)
    await client.put("/api/schedule", json={"mirea_id": 4805}, headers=auth())
    clock[0] = datetime(2026, 9, 30, 5, 0, tzinfo=UTC)  # Wednesday, 08:00 in Moscow
    body = (await client.get("/api/today", headers=auth(signed_at=clock[0]))).json()
    assert body["has_schedule"] is True and body["week_label"] == "5 неделя"
    assert body["lessons"] == [
        {
            "time": "12:40",
            "end": "14:10",
            "title": "Разработка баз данных",
            "kind": "ПР",
            "room": "И-212-б (В-78)",
            "starts_at": "2026-09-30T09:40:00Z",
            "ends_at": "2026-09-30T11:10:00Z",
        }
    ]
