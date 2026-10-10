from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from scripts.showcase import cdp

BIG = "x" * (5 * 1024 * 1024)  # past aiohttp's 4 MB limit for one message, like a 2× screenshot


async def devtools(request: web.Request) -> web.WebSocketResponse:
    """A browser's DevTools socket that answers as these tests need."""
    socket = web.WebSocketResponse(max_msg_size=0)
    await socket.prepare(request)
    held: list[dict[str, Any]] = []
    async for message in socket:
        command = json.loads(message.data)
        method, number = command["method"], command["id"]
        session = command.get("sessionId")
        if method == "Test.later":
            held.append(command)  # answered after the next command
        elif method == "Test.now":
            await socket.send_json({"id": number, "result": {"order": "first"}})
            for waiting in held:
                await socket.send_json({"id": waiting["id"], "result": {"order": "second"}})
        elif method == "Test.fail":
            await socket.send_json({"id": number, "error": {"code": -32000, "message": "No tab"}})
        elif method == "Test.big":
            await socket.send_json({"id": number, "result": {"data": BIG}})
        elif method == "Page.navigate":
            await socket.send_json({"method": "Page.loadEventFired", "sessionId": "other"})
            await socket.send_json({"id": number, "result": {"frameId": "1", "loaderId": "2"}})
            event = {"method": "Page.loadEventFired", "params": {"timestamp": 1}}
            await socket.send_json({**event, "sessionId": session})
        elif method == "Test.close":
            await socket.close()
        # Test.hang: never answered
    return socket


@pytest.fixture
async def connection() -> AsyncIterator[cdp.Connection]:
    app = web.Application()
    app.router.add_get("/devtools/browser/test", devtools)
    server = TestServer(app)
    await server.start_server()
    try:
        async with aiohttp.ClientSession() as client:
            opened = await cdp.Connection.open(
                client, str(server.make_url("/devtools/browser/test"))
            )
            try:
                yield opened
            finally:
                await opened.close()
    finally:
        await server.close()


async def test_answers_find_their_commands_in_any_order(connection: cdp.Connection) -> None:
    later = asyncio.create_task(connection.send("Test.later"))
    await asyncio.sleep(0.05)
    assert await connection.send("Test.now") == {"order": "first"}
    assert await later == {"order": "second"}


async def test_an_error_answer_names_the_command(connection: cdp.Connection) -> None:
    with pytest.raises(cdp.CommandError, match=r"Test\.fail: No tab"):
        await connection.send("Test.fail")


async def test_a_command_without_an_answer_runs_out_of_time(connection: cdp.Connection) -> None:
    with pytest.raises(cdp.CommandTimeout, match=r"Test\.hang: no answer in 0\.2 s"):
        await connection.send("Test.hang", limit=0.2)
    assert isinstance(cdp.CommandTimeout("Test.hang", 20), TimeoutError)  # a scene retries it
    assert cdp.TIMEOUT == 20


async def test_a_message_past_four_megabytes_arrives_whole(connection: cdp.Connection) -> None:
    assert (await connection.send("Test.big"))["data"] == BIG


async def test_a_page_waits_for_its_own_load_event(connection: cdp.Connection) -> None:
    page = cdp.Page(connection, "tab")
    await page.navigate("http://127.0.0.1/demo/")  # the other tab's event does not count


async def test_a_lost_connection_fails_what_waits_for_it(connection: cdp.Connection) -> None:
    waiting = asyncio.create_task(connection.send("Test.hang"))
    await asyncio.sleep(0.05)
    with pytest.raises(ConnectionError):
        await connection.send("Test.close")  # the browser goes away instead of answering
    with pytest.raises(ConnectionError):
        await waiting
    with pytest.raises(ConnectionError):
        await connection.send("Test.now")


async def test_a_scene_out_of_time_plays_once_more() -> None:
    played = []

    async def play() -> str:
        played.append(1)
        if len(played) == 1:
            raise cdp.CommandTimeout("Page.captureScreenshot", 20)
        return "frames"

    assert await cdp.scene("weather", play) == "frames"
    assert len(played) == 2


async def test_a_scene_out_of_time_twice_stops_the_run_with_its_name() -> None:
    async def play() -> None:
        raise cdp.CommandTimeout("Page.captureScreenshot", 20)

    with pytest.raises(cdp.SceneFailed, match="^money: Page.captureScreenshot"):
        await cdp.scene("money", play)


async def test_a_scene_that_fails_otherwise_is_not_played_again() -> None:
    played = []

    async def play() -> None:
        played.append(1)
        raise LookupError("no «habit link» on the screen")

    with pytest.raises(LookupError):
        await cdp.scene("habit", play)
    assert len(played) == 1


def test_the_browser_is_the_one_asked_for_then_the_usual_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given, variable, usual = (tmp_path / name for name in ("given.exe", "variable.exe", "edge"))
    for path in (given, variable, usual):
        path.write_bytes(b"")
    monkeypatch.setattr(cdp, "usual", lambda: [tmp_path / "missing", usual])
    monkeypatch.setenv("SHOWCASE_BROWSER", str(variable))
    assert cdp.find(str(given)) == given
    assert cdp.find(None) == variable
    monkeypatch.delenv("SHOWCASE_BROWSER")
    assert cdp.find(None) == usual
    with pytest.raises(cdp.BrowserError, match="nowhere.exe"):
        cdp.find(str(tmp_path / "nowhere.exe"))
    monkeypatch.setattr(cdp, "usual", lambda: [tmp_path / "missing"])
    with pytest.raises(cdp.BrowserError, match="--browser"):
        cdp.find(None)


def test_the_browser_is_named_with_its_version() -> None:
    assert cdp.name("Edg/155.0.4283.45") == "Microsoft Edge 155.0.4283.45"
    assert cdp.name("HeadlessChrome/141.0.7390.54") == "Chrome 141.0.7390.54"
    assert cdp.name("Chrome/141.0.7390.54") == "Chrome 141.0.7390.54"


def test_the_port_comes_from_the_profile(tmp_path: Path) -> None:
    assert cdp.active_port(tmp_path) is None
    (tmp_path / "DevToolsActivePort").write_text("59277\n", encoding="utf-8")
    assert cdp.active_port(tmp_path) is None  # written halfway
    (tmp_path / "DevToolsActivePort").write_text(
        "59277\n/devtools/browser/f4c4\n", encoding="utf-8"
    )
    assert cdp.active_port(tmp_path) == "ws://127.0.0.1:59277/devtools/browser/f4c4"


def test_the_flags_are_the_measured_ones() -> None:
    assert cdp.FLAGS == (
        "--headless",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        "--force-color-profile=srgb",
        "--mute-audio",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--remote-debugging-port=0",
    )
