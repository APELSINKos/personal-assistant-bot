from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from assistant.core import watchdog

linux_only = pytest.mark.skipif(
    sys.platform != "linux", reason="systemd's notify socket is a Unix datagram socket"
)


@pytest.fixture(params=["path", "abstract"])
def systemd(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[socket.socket]:
    """The notify socket systemd gives a service: a file, or a name in the abstract namespace
    (NOTIFY_SOCKET starts with "@" then)."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    if request.param == "path":
        sock.bind(str(tmp_path / "notify"))
        monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "notify"))
    else:
        name = f"assistant-test-{os.getpid()}"
        sock.bind("\0" + name)
        monkeypatch.setenv("NOTIFY_SOCKET", "@" + name)
    sock.setblocking(False)
    monkeypatch.setattr(watchdog, "PERIOD", 0.01)
    yield sock
    sock.close()


def received(sock: socket.socket) -> list[str]:
    messages = []
    while True:
        try:
            messages.append(sock.recv(4096).decode())
        except BlockingIOError:
            return messages


@linux_only
async def test_turns_the_watchdog_on_and_feeds_it(systemd: socket.socket) -> None:
    task = asyncio.create_task(watchdog.keep_alive())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.wait({task})
    messages = received(systemd)
    # Two minutes without a keep-alive and systemd kills the service; four of them per timeout.
    assert messages[0] == "WATCHDOG_USEC=120000000"
    assert messages[1:] and set(messages[1:]) == {"WATCHDOG=1"}


@linux_only
async def test_stops_feeding_once_the_scheduler_is_stuck(
    systemd: socket.socket, caplog: pytest.LogCaptureFixture
) -> None:
    task = asyncio.create_task(watchdog.keep_alive(lambda: False))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.wait({task})
    assert received(systemd) == ["WATCHDOG_USEC=120000000"]
    assert "the service is stuck: systemd's watchdog is no longer fed" in caplog.messages


async def test_does_nothing_outside_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    await asyncio.wait_for(watchdog.keep_alive(), timeout=1)  # returns at once
    assert not watchdog.notify("WATCHDOG=1")


async def test_a_socket_out_of_reach_leaves_the_service_unwatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "nowhere"))
    await asyncio.wait_for(watchdog.keep_alive(), timeout=1)  # no error, and no watchdog
    assert not watchdog.notify("WATCHDOG=1")
    assert not caplog.messages
