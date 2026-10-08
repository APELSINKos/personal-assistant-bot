"""systemd's watchdog for the bot and the API, through sd_notify without a dependency.

The process turns the watchdog on itself (WATCHDOG_USEC=) and then feeds it: WatchdogSec= in a
unit file would also watch an older commit after a rollback, which never feeds it and would be
killed every two minutes. A frozen event loop stops the keep-alives, and so does a service whose
alive() says it is stuck: systemd kills the process (SIGABRT, result "watchdog") and
Restart=always starts it again."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)

# No keep-alive for this long, and systemd kills the service.
TIMEOUT = 120.0
# Four keep-alives per TIMEOUT: a loop that is merely busy for a minute is not killed.
PERIOD = 30.0


def notify(message: str) -> bool:
    """Sends systemd one sd_notify message; False outside systemd (no NOTIFY_SOCKET) or when
    the socket cannot be reached."""
    if sys.platform == "win32":
        return False  # no systemd there
    address = os.environ.get("NOTIFY_SOCKET", "")
    if not address:
        return False
    if address.startswith("@"):  # a name in the abstract namespace
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), address)
    except OSError:
        return False
    return True


async def keep_alive(alive: Callable[[], bool] = lambda: True) -> None:
    """Turns systemd's watchdog on for this service and feeds it every PERIOD while alive()
    says so. Returns at once when not run by systemd; cancel it on shutdown."""
    if not notify(f"WATCHDOG_USEC={round(TIMEOUT * 1_000_000)}"):
        return
    log.info("systemd watchdog on: %.0f s", TIMEOUT)
    while True:
        if alive():
            notify("WATCHDOG=1")
        else:
            log.warning("the service is stuck: systemd's watchdog is no longer fed")
        await asyncio.sleep(PERIOD)
