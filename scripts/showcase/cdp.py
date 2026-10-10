"""A headless Edge or Chrome for the README's pictures, driven over the DevTools protocol on
aiohttp (spec §13.1): it starts with a profile of its own in the run's temporary folder, takes
commands over one WebSocket and ends with everything it started.

Each rule here comes from a failure measured while the generator was designed. A long session
slows down and then hangs, so every scene starts a browser of its own. A command gets 20 s, and a
scene that runs out of time plays once more before the run stops with its name. A screenshot at
2× can be larger than aiohttp's 4 MB for one message, so the socket takes any size. The browser
goes with the generator even when that is killed from outside: on Windows it runs in a job object
that ends it as the generator's handle to the job closes, on POSIX in a process group of its own.
A browser is never ended by name, only the processes that carry this run's profile.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ctypes
import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp

TIMEOUT = 20.0  # seconds for any command
FLAGS = (
    "--headless",
    "--no-first-run",
    "--no-default-browser-check",
    "--hide-scrollbars",
    "--force-color-profile=srgb",
    "--mute-audio",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--remote-debugging-port=0",  # the port it takes is written into the profile
)


class BrowserError(RuntimeError):
    """No browser to run, or one that did not start or open an address."""


class CommandError(RuntimeError):
    """The browser answered a command with an error."""


class PageError(RuntimeError):
    """A script in the page threw."""


class CommandTimeout(TimeoutError):
    def __init__(self, method: str, limit: float) -> None:
        super().__init__(f"{method}: no answer in {limit:g} s")


class SceneFailed(RuntimeError):
    """A scene ran out of time twice: the run stops with its name."""


def usual() -> list[Path]:
    """Where Edge and then Chrome usually are: both Program Files folders on Windows, the PATH
    elsewhere."""
    if sys.platform == "win32":
        folders = [os.environ.get(name) for name in ("ProgramFiles(x86)", "ProgramFiles")]
        apps = (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")
        return [Path(folder) / app for app in apps for folder in folders if folder]
    names = ("google-chrome", "chromium", "microsoft-edge")
    return [Path(found) for name in names if (found := shutil.which(name))]


def find(given: str | None) -> Path:
    """The browser: --browser, else SHOWCASE_BROWSER, else Edge or Chrome where they usually are."""
    asked = given or os.environ.get("SHOWCASE_BROWSER")
    if asked:
        found = asked if Path(asked).is_file() else shutil.which(asked)
        if found is None:
            raise BrowserError(f"no browser at {asked}")
        return Path(found)
    for path in usual():
        if path.is_file():
            return path
    raise BrowserError("no Edge or Chrome found: name one with --browser or SHOWCASE_BROWSER")


def name(product: str) -> str:
    """«Microsoft Edge 155.0.4283.45» from what Browser.getVersion calls the product."""
    kind, _, version = product.partition("/")
    return f"{'Microsoft Edge' if kind == 'Edg' else 'Chrome'} {version}"


def active_port(profile: Path) -> str | None:
    """The browser's DevTools address once it has written it into the profile: the port on the
    first line of DevToolsActivePort, the browser's path on the second."""
    try:
        lines = (profile / "DevToolsActivePort").read_text(encoding="utf-8").split()
    except OSError:
        return None
    return f"ws://127.0.0.1:{lines[0]}{lines[1]}" if len(lines) >= 2 else None


class Connection:
    """One WebSocket to the browser: commands go out numbered, answers come back by their
    numbers, and an event goes to whoever waits for it."""

    def __init__(self, socket: aiohttp.ClientWebSocketResponse) -> None:
        self._socket = socket
        self._numbers = itertools.count(1)
        self._answers: dict[int, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
        self._events: list[tuple[str | None, str, asyncio.Future[dict[str, Any]]]] = []
        self._lost: str | None = None
        self._reader = asyncio.create_task(self._read())

    @classmethod
    async def open(cls, client: aiohttp.ClientSession, url: str) -> Connection:
        return cls(await client.ws_connect(url, max_msg_size=0))  # a 2× screenshot passes 4 MB

    async def _read(self) -> None:
        try:
            async for message in self._socket:
                if message.type is aiohttp.WSMsgType.TEXT:
                    self._take(json.loads(message.data))
            self._lost = "the browser closed its DevTools connection"
        except Exception as error:  # whatever it was, it reaches those who wait
            self._lost = f"the DevTools connection broke: {error!r}"
        finally:
            self._lost = self._lost or "the DevTools connection was closed"
            waiting = [future for _, future in self._answers.values()]
            waiting += [future for _, _, future in self._events]
            for future in waiting:
                if not future.done():
                    future.set_exception(ConnectionError(self._lost))
            self._answers.clear()
            self._events.clear()

    def _take(self, data: dict[str, Any]) -> None:
        if "id" in data:
            method, future = self._answers.pop(data["id"], ("", None))
            if future is None or future.done():
                return
            if "error" in data:
                future.set_exception(CommandError(f"{method}: {data['error'].get('message')}"))
            else:
                future.set_result(data.get("result", {}))
            return
        key = (data.get("sessionId"), data.get("method"))
        for entry in list(self._events):
            if entry[2].done():
                self._events.remove(entry)
            elif entry[:2] == key:
                self._events.remove(entry)
                entry[2].set_result(data.get("params", {}))

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session: str | None = None,
        limit: float = TIMEOUT,
    ) -> dict[str, Any]:
        """The answer to a command, to the browser or, with a session, to one of its tabs."""
        if self._lost:
            raise ConnectionError(self._lost)
        number = next(self._numbers)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._answers[number] = (method, future)
        message: dict[str, Any] = {"id": number, "method": method, "params": params or {}}
        if session is not None:
            message["sessionId"] = session
        try:
            await self._socket.send_str(json.dumps(message))
            return await asyncio.wait_for(future, limit)
        except TimeoutError:
            raise CommandTimeout(method, limit) from None
        finally:
            self._answers.pop(number, None)

    def expect(self, method: str, *, session: str | None = None) -> asyncio.Future[dict[str, Any]]:
        """The next event `method` of the session; ask before the command that brings it."""
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        if self._lost:
            future.set_exception(ConnectionError(self._lost))
        else:
            self._events.append((session, method, future))
        return future

    async def close(self) -> None:
        self._reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reader
        await self._socket.close()


class Page:
    """A tab of the browser, through its session on the browser's connection."""

    def __init__(self, connection: Connection, session: str) -> None:
        self.connection, self.session = connection, session

    async def send(
        self, method: str, params: dict[str, Any] | None = None, *, limit: float = TIMEOUT
    ) -> dict[str, Any]:
        return await self.connection.send(method, params, session=self.session, limit=limit)

    async def evaluate(self, expression: str) -> Any:
        """The value of a script in the page; a promise it gives is awaited."""
        answer = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        if "exceptionDetails" in answer:
            details = answer["exceptionDetails"]
            raise PageError(details.get("exception", {}).get("description") or details["text"])
        return answer["result"].get("value")

    async def navigate(self, url: str) -> None:
        """Opens the address and waits for its load event."""
        loaded = self.connection.expect("Page.loadEventFired", session=self.session)
        answer = await self.send("Page.navigate", {"url": url})
        if answer.get("errorText") or "loaderId" not in answer:
            loaded.cancel()  # an error, or a new hash only: no new document comes
            if answer.get("errorText"):
                raise BrowserError(f"{url}: {answer['errorText']}")
            return
        try:
            await asyncio.wait_for(loaded, TIMEOUT)
        except TimeoutError:
            raise CommandTimeout("Page.loadEventFired", TIMEOUT) from None

    async def screenshot(self, **params: Any) -> bytes:
        return base64.b64decode((await self.send("Page.captureScreenshot", params))["data"])


class Browser:
    """A headless browser of this run, with its own profile."""

    def __init__(self, executable: Path, profile: Path) -> None:
        self.executable, self.profile = executable, profile
        self.process: subprocess.Popen[bytes] | None = None
        self._job: int | None = None
        self._client: aiohttp.ClientSession | None = None
        self._connection: Connection | None = None

    @property
    def connection(self) -> Connection:
        assert self._connection is not None, "the browser has not started"
        return self._connection

    async def start(self) -> None:
        command = [str(self.executable), *FLAGS, f"--user-data-dir={self.profile}", "about:blank"]
        self.process, self._job = _spawn(command)
        address = None
        for _ in range(int(TIMEOUT / 0.05)):
            address = active_port(self.profile)
            if address or self.process.poll() is not None:
                break
            await asyncio.sleep(0.05)
        if address is None:
            if self.process.poll() is not None:
                raise BrowserError(f"{self.executable.name} exited with {self.process.returncode}")
            raise TimeoutError(f"{self.executable.name} opened no DevTools port in {TIMEOUT:g} s")
        self._client = aiohttp.ClientSession()
        self._connection = await Connection.open(self._client, address)

    async def version(self) -> str:
        return name((await self.connection.send("Browser.getVersion"))["product"])

    async def page(self) -> Page:
        """The browser's tab, with its page events on."""
        targets = (await self.connection.send("Target.getTargets"))["targetInfos"]
        tab = next((target["targetId"] for target in targets if target["type"] == "page"), None)
        if tab is None:
            tab = (await self.connection.send("Target.createTarget", {"url": "about:blank"}))[
                "targetId"
            ]
        attached = await self.connection.send(
            "Target.attachToTarget", {"targetId": tab, "flatten": True}
        )
        page = Page(self.connection, attached["sessionId"])
        await page.send("Page.enable")
        return page

    async def close(self) -> None:
        """Browser.close, then whatever of this run is left, then the profile."""
        asked = False
        if self._connection is not None:
            with contextlib.suppress(
                CommandError, ConnectionError, TimeoutError, aiohttp.ClientError
            ):
                await self._connection.send("Browser.close", limit=5)
                asked = True
            await self._connection.close()
        if self._client is not None:
            await self._client.close()
        if self.process is not None:
            grace = 10 if asked else 0  # the time a closing browser gets to end itself
            await asyncio.to_thread(_end, self.process, self._job, self.profile.name, grace)
        await asyncio.to_thread(_remove, self.profile)


@contextlib.asynccontextmanager
async def launch(executable: Path, folder: Path) -> AsyncIterator[Browser]:
    """A fresh headless browser with a profile of its own in `folder`, ended with everything it
    started when the block ends, however it ends."""
    browser = Browser(executable, Path(tempfile.mkdtemp(prefix="profile-", dir=folder)))
    try:
        await browser.start()
        yield browser
    finally:
        await browser.close()


async def scene[T](name: str, play: Callable[[], Awaitable[T]]) -> T:
    """Plays a scene that starts a browser of its own. One that runs out of time plays once more,
    and if it runs out of time again, the run stops with the scene's name."""
    try:
        return await play()
    except TimeoutError as error:
        print(f"{name}: {error}; once more")
    try:
        return await play()
    except TimeoutError as error:
        raise SceneFailed(f"{name}: {error}") from error


def _spawn(command: list[str]) -> tuple[subprocess.Popen[bytes], int | None]:
    quiet = subprocess.DEVNULL
    if sys.platform != "win32":
        process = subprocess.Popen(
            command, stdin=quiet, stdout=quiet, stderr=quiet, start_new_session=True
        )
        return process, None
    job = _job()
    try:
        process = subprocess.Popen(command, stdin=quiet, stdout=quiet, stderr=quiet)
    except OSError:
        _kernel32().CloseHandle(job)
        raise
    try:
        # At once: the browser has to load itself before it can start a child of its own.
        _assign(job, process.pid)
    except OSError:
        process.kill()
        _kernel32().CloseHandle(job)
        raise
    return process, job


def _end(process: subprocess.Popen[bytes], job: int | None, profile: str, grace: float) -> None:
    """Ends what is left of this run's browser once it had `grace` seconds to end itself: on
    Windows every process of its job, then any process whose command line holds its profile; on
    POSIX its process group."""
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(grace)
    if sys.platform != "win32":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(5)
        return
    if job is not None:
        _kernel32().CloseHandle(job)  # ends every process still in the job
    ended = _end_by_profile(profile)
    if ended:
        print(f"Ended {len(ended)} processes left by the browser of {profile}")


def _remove(profile: Path) -> None:
    """Removes the profile; a file an ending process still holds is let go a moment later."""
    for _ in range(40):
        try:
            shutil.rmtree(profile)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.25)
    print(f"The browser's profile stays until the end of the run: {profile}")


# Windows: a job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, through ctypes.


class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _Limits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


KILL_ON_JOB_CLOSE = 0x2000
EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation
SET_QUOTA_AND_TERMINATE = 0x0100 | 0x0001


def _kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    kernel32.CreateJobObjectW.restype = handle
    kernel32.CreateJobObjectW.argtypes = (handle, ctypes.c_wchar_p)
    kernel32.SetInformationJobObject.argtypes = (handle, ctypes.c_int, handle, ctypes.c_uint32)
    kernel32.OpenProcess.restype = handle
    kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.AssignProcessToJobObject.argtypes = (handle, handle)
    kernel32.CloseHandle.argtypes = (handle,)
    return kernel32


def _job() -> int:
    """A job object that ends its processes, and the processes they start, when its last handle
    closes: the generator's, which closes with the generator however that ends."""
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _Limits()
    limits.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job, EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(job)
        raise error
    return int(job)


def _assign(job: int, pid: int) -> None:
    kernel32 = _kernel32()
    process = kernel32.OpenProcess(SET_QUOTA_AND_TERMINATE, False, pid)
    try:
        if not process or not kernel32.AssignProcessToJobObject(job, process):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if process:
            kernel32.CloseHandle(process)


# The profile reaches PowerShell through its environment, so its own command line does not hold it.
_LEFTOVERS = (
    "$mark = $env:SHOWCASE_PROFILE; "
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($mark) } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "
    "$_.ProcessId }"
)


def _end_by_profile(profile: str) -> list[int]:
    """Ends each process whose command line holds the profile's name, and only those: a CIM
    query through PowerShell, since Windows 11 has no wmic."""
    try:
        answer = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _LEFTOVERS],
            capture_output=True,
            text=True,
            env={**os.environ, "SHOWCASE_PROFILE": profile},
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Could not look for processes left by the browser: {error}")
        return []
    return [int(line) for line in answer.stdout.split() if line.isdigit()]
