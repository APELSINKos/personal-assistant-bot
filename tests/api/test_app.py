from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

import assistant
from assistant.api import __main__ as entry
from assistant.api.app import create_app
from assistant.api.ratelimit import RateLimiter
from assistant.api.routers.health import read_commit
from assistant.core.models import User
from tests.api.conftest import NOW
from tests.stubs import StubCalendars

PROBLEM = "application/problem+json"


async def test_health_needs_no_auth(client) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": assistant.__version__, "commit": "0" * 40}


async def test_openapi_schema_is_served(client) -> None:
    assert (await client.get("/api/openapi.json")).status_code == 200


@pytest.mark.parametrize("header", [None, "Bearer x", "tma ", "tma garbage"])
async def test_missing_or_bad_auth_is_a_401_problem(client, header) -> None:
    headers = {"Authorization": header} if header is not None else {}
    response = await client.get("/api/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith(PROBLEM)
    body = response.json()
    assert body["code"] == "invalid_init_data" and body["status"] == 401


async def test_expired_init_data_is_401(client, auth) -> None:
    response = await client.get("/api/me", headers=auth(signed_at=NOW - timedelta(days=2)))
    assert response.status_code == 401 and response.json()["code"] == "expired_init_data"


async def test_first_request_creates_user_with_telegram_language(client, auth, session) -> None:
    response = await client.get("/api/me", headers=auth(77, first_name="Nina", lang="en"))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 77 and body["first_name"] == "Nina"
    assert body["language"] == "en" and body["language_setting"] == "auto"
    assert body["city"]["name"] == "Москва" and body["morning"] == {
        "enabled": True,
        "time": "08:00",
    }
    user = await session.get(User, 77)
    assert user is not None and user.tg_language == "en"


async def test_new_user_first_open_sends_requests_at_once(client, auth, session) -> None:
    # The app asks for /me and /today in the same tick; neither may trip over the other.
    for user_id in range(300, 305):
        me, today = await asyncio.gather(
            client.get("/api/me", headers=auth(user_id)),
            client.get("/api/today", headers=auth(user_id)),
        )
        assert (me.status_code, today.status_code) == (200, 200)
    count = await session.scalar(select(func.count()).select_from(User))
    assert count == 5


async def test_rate_limit_is_a_429_problem(sessionmaker, api_settings, meteo, cbr, auth) -> None:
    app = create_app(
        settings=api_settings,
        sessionmaker=sessionmaker,
        meteo=meteo,
        cbr=cbr,
        calendars=StubCalendars(),
        clock=lambda: NOW,
        limiter=RateLimiter(2),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        codes = [(await http.get("/api/me", headers=auth())).status_code for _ in range(3)]
        limited = await http.get("/api/me", headers=auth())
    assert codes == [200, 200, 429]
    assert limited.json()["code"] == "rate_limited" and int(limited.headers["Retry-After"]) >= 1


async def test_request_validation_is_a_422_problem(app, client) -> None:
    @app.get("/api/_probe/{number}")
    async def probe(number: int) -> dict[str, int]:
        return {"number": number}

    response = await client.get("/api/_probe/abc")
    assert response.status_code == 422 and response.headers["content-type"].startswith(PROBLEM)
    assert response.json()["code"] == "validation_error" and response.json()["field"] == "number"


async def test_unknown_route_is_a_404_problem(client) -> None:
    response = await client.get("/api/nothing-here")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


async def test_internal_errors_hide_details(app, client) -> None:
    @app.get("/api/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    response = await client.get("/api/_boom")
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "secret" not in response.text


async def test_internal_error_is_logged_as_one_line(app, client, caplog) -> None:
    @app.get("/api/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    with caplog.at_level(logging.ERROR):
        await client.get("/api/_boom")
    # The server logs the traceback once when the error propagates; the handler adds no second.
    records = [record for record in caplog.records if record.name == "assistant.api.errors"]
    assert [record.getMessage() for record in records] == ["request GET /api/_boom failed"]
    assert records[0].exc_info is None and records[0].exc_text is None


def test_read_commit(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    assert read_commit(tmp_path / "nowhere") is None
    (git / "HEAD").write_text("a" * 40 + "\n")
    assert read_commit(tmp_path) == "a" * 40
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text("# pack-refs\n" + "b" * 40 + " refs/heads/main\n")
    assert read_commit(tmp_path) == "b" * 40
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "refs" / "heads" / "main").write_text("c" * 40 + "\n")
    assert read_commit(tmp_path) == "c" * 40


async def test_api_gives_upstream_services_a_short_time_budget(monkeypatch, api_settings) -> None:
    timeouts: list[object] = []
    real_client = httpx.AsyncClient

    def recording_client(*, timeout: float) -> httpx.AsyncClient:
        timeouts.append(timeout)
        return real_client(timeout=timeout)

    class NoServer:
        def __init__(self, config: object) -> None:
            pass

        async def serve(self) -> None:
            pass

    monkeypatch.setattr(entry, "get_settings", lambda: api_settings)
    monkeypatch.setattr(entry, "setup_logging", lambda *args: None)
    monkeypatch.setattr(entry.httpx, "AsyncClient", recording_client)
    monkeypatch.setattr(entry.uvicorn, "Server", NoServer)
    await entry.main()
    # «Сегодня» must not wait for a hanging upstream as long as the bot may.
    assert timeouts == [4.0] and api_settings.http_timeout == 10.0
