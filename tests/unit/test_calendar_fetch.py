from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable

import httpx
import pytest

from assistant.core.clients.calendars import CalendarFetcher, is_public, normalize
from assistant.core.errors import InvalidInput

ICS = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
PUBLIC = "93.184.215.14"


def resolver(table: dict[str, list[str]]) -> Callable[[str, int], Awaitable[list[str]]]:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise socket.gaierror("no such host")
        return table[host]

    return resolve


def fetcher(handler, table: dict[str, list[str]] | None = None, **kwargs) -> CalendarFetcher:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CalendarFetcher(http, resolver(table or {"uni.example": [PUBLIC]}), **kwargs)


async def reason(call: Awaitable[bytes]) -> str:
    with pytest.raises(InvalidInput) as caught:
        await call
    assert caught.value.params["field"] == "url"
    return str(caught.value.params["reason"])


async def test_downloads_from_the_checked_address_with_the_name_in_host_and_sni() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ICS, headers={"Content-Type": "text/calendar"})

    body = await fetcher(handler).fetch("webcal://uni.example/timetable.ics?group=5")
    assert body == ICS
    (request,) = seen
    assert request.url.scheme == "https" and request.url.host == PUBLIC
    assert request.url.path == "/timetable.ics" and request.url.query == b"group=5"
    assert request.headers["host"] == "uni.example"
    assert request.extensions["sni_hostname"] == "uni.example"
    assert "personal-assistant-bot" in request.headers["user-agent"]


@pytest.mark.parametrize(
    "url",
    [
        "http://uni.example/a.ics",
        "ftp://uni.example/a.ics",
        "https://uni.example:8443/a.ics",
        "https://user:secret@uni.example/a.ics",
        "https:///a.ics",
        "file:///etc/passwd",
        "https://uni.example/" + "a" * 2000,
        "not a link",
    ],
)
async def test_only_plain_https_links(url: str) -> None:
    assert await reason(fetcher(lambda request: httpx.Response(200)).fetch(url)) == "forbidden_host"


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.1.2.3"],
        ["172.31.0.2"],
        ["192.168.0.10"],
        ["169.254.169.254"],  # cloud instance metadata
        ["100.64.0.1"],  # carrier-grade NAT
        ["::1"],
        ["fd00::1"],
        ["::ffff:10.0.0.1"],
        [PUBLIC, "10.0.0.1"],  # one private address is enough to refuse
        [],
    ],
)
async def test_hosts_that_resolve_inside_are_refused(addresses: list[str]) -> None:
    calls: list[httpx.Request] = []
    handler = lambda request: calls.append(request) or httpx.Response(200, content=ICS)  # noqa: E731
    got = await reason(fetcher(handler, {"uni.example": addresses}).fetch("https://uni.example/a"))
    assert got == "forbidden_host" and calls == []


@pytest.mark.parametrize("url", ["https://127.0.0.1/a.ics", "https://[::1]/a.ics"])
async def test_literal_inside_addresses_are_refused(url: str) -> None:
    assert await reason(fetcher(lambda request: httpx.Response(200)).fetch(url)) == "forbidden_host"


async def test_a_redirect_inside_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://internal.example/secret"})

    table = {"uni.example": [PUBLIC], "internal.example": ["10.0.0.7"]}
    assert await reason(fetcher(handler, table).fetch("https://uni.example/a")) == "forbidden_host"


async def test_a_redirect_to_http_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "http://uni.example/a.ics"})

    assert await reason(fetcher(handler).fetch("https://uni.example/a")) == "forbidden_host"


async def test_redirects_are_followed_three_times_at_most() -> None:
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(request.url.path)
        if len(hops) <= 3:
            return httpx.Response(302, headers={"Location": f"/hop{len(hops)}"})
        return httpx.Response(200, content=ICS)

    assert await fetcher(handler).fetch("https://uni.example/start") == ICS
    assert hops == ["/start", "/hop1", "/hop2", "/hop3"]

    hops.clear()

    def endless(request: httpx.Request) -> httpx.Response:
        hops.append(request.url.path)
        return httpx.Response(302, headers={"Location": f"/hop{len(hops)}"})

    assert await reason(fetcher(endless).fetch("https://uni.example/start")) == "unreachable"
    assert len(hops) == 4


async def test_a_body_over_the_limit_is_too_large() -> None:
    handler = lambda request: httpx.Response(200, content=b"B" * 5000)  # noqa: E731
    got = await reason(fetcher(handler, max_bytes=4096).fetch("https://uni.example/a"))
    assert got == "too_large"


async def test_head_reads_only_the_beginning() -> None:
    handler = lambda request: httpx.Response(200, content=ICS + b"X" * 10_000)  # noqa: E731
    assert await fetcher(handler).head("https://uni.example/a", limit=20) == ICS[:20]


@pytest.mark.parametrize("status", [404, 403, 500])
async def test_http_errors_are_unreachable(status: int) -> None:
    handler = lambda request: httpx.Response(status)  # noqa: E731
    assert await reason(fetcher(handler).fetch("https://uni.example/a")) == "unreachable"


async def test_network_and_dns_failures_are_unreachable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    assert await reason(fetcher(down).fetch("https://uni.example/a")) == "unreachable"
    ok = lambda request: httpx.Response(200, content=ICS)  # noqa: E731
    assert await reason(fetcher(ok, {}).fetch("https://nowhere.example/a")) == "unreachable"


async def test_a_slow_server_is_unreachable() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, content=ICS)

    got = await reason(fetcher(slow, timeout=0.05).fetch("https://uni.example/a"))
    assert got == "unreachable"


def test_normalize_and_public_helpers() -> None:
    assert str(normalize(" WEBCAL://uni.example/a.ics ")) == "https://uni.example/a.ics"
    assert is_public(PUBLIC) and not is_public("192.168.1.1") and not is_public("::ffff:127.0.0.1")
