from __future__ import annotations

import asyncio
import functools
import gzip
import ipaddress
import socket
import struct
import tracemalloc
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from assistant.core.clients.calendars import (
    MAX_BYTES,
    CalendarFetcher,
    calendar_client,
    is_public,
    normalize,
)
from assistant.core.errors import InvalidInput

ICS = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
PUBLIC = "93.184.215.14"
MIB = 2**20
MOST_PIECES = 65_536  # raw pieces (network reads) one download may take


def resolver(table: dict[str, list[str]]) -> Callable[[str, int], Awaitable[list[str]]]:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise socket.gaierror("no such host")
        return table[host]

    return resolve


class Body(httpx.AsyncByteStream):
    """A response body as a server streams it, a network read at a time; notes being read."""

    def __init__(self, data: bytes, piece: int = 64 * 1024) -> None:
        self.data, self.piece, self.read = data, piece, False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.read = True
        for start in range(0, len(self.data), self.piece):
            yield self.data[start : start + self.piece]


def fetcher(handler, table: dict[str, list[str]] | None = None, **kwargs) -> CalendarFetcher:
    async def streamed(request: httpx.Request) -> httpx.Response:
        response = handler(request)
        if not isinstance(response, httpx.Response):
            response = await response
        if response.is_stream_consumed:
            # Response(content=…) comes back already read; a real transport streams the body,
            # and the fetcher reads it raw.
            response = httpx.Response(
                response.status_code, headers=response.headers, stream=Body(response.content)
            )
        return response

    http = httpx.AsyncClient(transport=httpx.MockTransport(streamed))
    return CalendarFetcher(http, resolver(table or {"uni.example": [PUBLIC]}), **kwargs)


def coded(body: Body, *codings: str) -> Callable[[httpx.Request], httpx.Response]:
    """A server that sends `body` with one Content-Encoding header per coding."""
    headers = [("Content-Encoding", coding) for coding in codings]
    return lambda request: httpx.Response(200, headers=headers, stream=body)


@functools.cache
def gzip_bomb(mebibytes: int) -> bytes:
    """A valid gzip file of `mebibytes` MiB of zeros, about 1 KiB per MiB."""
    zeros = bytes(MIB)
    deflate = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    # A full flush makes the compressed MiB stand alone, so its bytes can simply repeat.
    block = deflate.compress(zeros) + deflate.flush(zlib.Z_FULL_FLUSH)
    crc = 0
    for _ in range(mebibytes):
        crc = zlib.crc32(zeros, crc)
    header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    trailer = struct.pack("<II", crc, mebibytes * MIB % 2**32)
    return header + block * mebibytes + deflate.flush() + trailer


def raw_deflate(data: bytes) -> bytes:
    deflate = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return deflate.compress(data) + deflate.flush()


def gzip_with_comment(data: bytes, size: int) -> bytes:
    """A gzip member of `data` whose header carries a comment (FCOMMENT) of `size` bytes."""
    header = b"\x1f\x8b\x08\x10\x00\x00\x00\x00\x00\xff" + b"c" * size + b"\x00"
    trailer = struct.pack("<II", zlib.crc32(data), len(data) % 2**32)
    return header + raw_deflate(data) + trailer


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


async def test_an_idn_host_goes_out_in_its_ascii_form() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ICS)

    # The resolver knows only the A-labels: header values must be ASCII, and httpx itself
    # encodes the name by IDNA 2008, where the system resolver would use IDNA 2003.
    table = {"xn--e1afmkfd.xn--p1ai": [PUBLIC]}
    assert await fetcher(handler, table).fetch("https://пример.рф/cal.ics") == ICS
    (request,) = seen
    assert request.url.host == PUBLIC
    assert request.headers["host"] == "xn--e1afmkfd.xn--p1ai"
    assert request.extensions["sni_hostname"] == "xn--e1afmkfd.xn--p1ai"


async def test_an_ipv6_literal_goes_in_host_with_brackets() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ICS)

    assert await fetcher(handler).fetch("https://[2606:4700:4700::1111]/cal.ics") == ICS
    (request,) = seen
    assert request.url.host == "2606:4700:4700::1111"
    assert request.headers["host"] == "[2606:4700:4700::1111]"
    assert request.extensions["sni_hostname"] == "2606:4700:4700::1111"


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
        ["::"],
        ["::127.0.0.1"],  # IPv4-compatible
        ["::10.0.0.1"],
        ["64:ff9b::10.0.0.1"],  # NAT64: what DNS64 makes of an A record pointing inside
        ["64:ff9b::169.254.169.254"],
        ["::ffff:0:10.0.0.1"],  # IPv4-translated
        ["fec0::1"],  # site-local, deprecated
        ["2002:a00:1::1"],  # 6to4, here of 10.0.0.1
        ["2002:5db8:d70e::1"],  # 6to4 of a public address: a relay's business, not ours
        ["2001:0:4136:e378:8000:63bf:3fff:fdd2"],  # Teredo
        [PUBLIC, "10.0.0.1"],  # one private address is enough to refuse
        [],
    ],
)
async def test_hosts_that_resolve_inside_are_refused(addresses: list[str]) -> None:
    calls: list[httpx.Request] = []
    handler = lambda request: calls.append(request) or httpx.Response(200, content=ICS)  # noqa: E731
    got = await reason(fetcher(handler, {"uni.example": addresses}).fetch("https://uni.example/a"))
    assert got == "forbidden_host" and calls == []


async def test_a_nat64_address_of_a_public_ipv4_is_allowed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ICS)

    table = {"uni.example": ["64:ff9b::93.184.215.14"]}
    assert await fetcher(handler, table).fetch("https://uni.example/a") == ICS
    assert seen[0].url.host == "64:ff9b::93.184.215.14"


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


@pytest.mark.parametrize("call", ["fetch", "head"])
@pytest.mark.parametrize(
    "location", ["https:x", "https:uni.example/cal.ics", "mailto:someone@example.com", "webcal:x"]
)
async def test_a_redirect_to_a_link_without_a_host_is_unreachable(location: str, call: str) -> None:
    # A scheme, no host and a path without "/": preparing the next hop, httpx gives the link our
    # host, and its own URL check then raises InvalidURL outside its try.
    handler = lambda request: httpx.Response(302, headers={"Location": location})  # noqa: E731
    calendars = fetcher(handler)
    assert await reason(getattr(calendars, call)("https://uni.example/a")) == "unreachable"


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


@pytest.mark.parametrize(
    ("coding", "body"),
    [
        ("gzip", gzip.compress(ICS, mtime=0)),
        ("x-gzip", gzip.compress(ICS, mtime=0)),
        ("deflate", zlib.compress(ICS)),  # zlib-wrapped, as the RFC means it
        ("deflate", raw_deflate(ICS)),  # bare, as some servers send it
        ("identity", ICS),
    ],
    ids=["gzip", "x-gzip", "deflate", "raw-deflate", "identity"],
)
async def test_one_gzip_or_deflate_layer_sent_anyway_is_decoded(coding: str, body: bytes) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return coded(Body(body, piece=7), coding)(request)

    assert await fetcher(handler).fetch("https://uni.example/a") == ICS
    assert seen[0].headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    "codings",
    [("gzip, gzip",), ("gzip", "gzip"), ("deflate, gzip",), ("br",), ("zstd",), ("compress",)],
    ids=["gzip,gzip", "gzip+gzip-headers", "deflate,gzip", "br", "zstd", "compress"],
)
async def test_stacked_or_unknown_codings_are_refused_unread(codings: tuple[str, ...]) -> None:
    # 232 bytes that two gzip layers turn into 64 MiB; httpx would undo both in one call.
    body = Body(gzip.compress(gzip_bomb(64), mtime=0))
    got = await reason(fetcher(coded(body, *codings)).fetch("https://uni.example/a"))
    assert got == "unreachable" and not body.read


async def test_a_gzip_bomb_stops_at_the_limit() -> None:
    # 66 KB, about one network read, that gzip turns into 64 MiB of zeros.
    calendars = fetcher(coded(Body(gzip_bomb(64)), "gzip"))
    tracemalloc.start()
    try:
        got = await reason(calendars.fetch("https://uni.example/a"))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert got == "too_large"
    # Undone a whole network read at a time it peaked at ~141 MiB; capped at the limit, ~4.2.
    assert peak < 4 * MAX_BYTES


async def test_head_of_a_gzip_bomb_decodes_only_the_beginning() -> None:
    calendars = fetcher(coded(Body(gzip_bomb(64)), "gzip"))
    tracemalloc.start()
    try:
        head = await calendars.head("https://uni.example/a", limit=4096)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert head == bytes(4096)
    # ~141 MiB before as well; now ~0.2 MiB.
    assert peak < MIB


async def test_raw_bytes_past_the_limit_are_too_large_even_if_they_decode_to_little() -> None:
    # A gzip member whose header carries 200 KB of comment: the decoder reads it all, giving
    # nothing, before the calendar starts.
    body = Body(gzip_with_comment(ICS, 200_000))
    got = await reason(fetcher(coded(body, "gzip"), max_bytes=4096).fetch("https://uni.example/a"))
    assert got == "too_large"


class Drip(httpx.AsyncByteStream):
    """`head` in one piece, then `count` pieces of one byte each; notes how many were read."""

    def __init__(self, head: bytes, count: int) -> None:
        self.head, self.count, self.pulled = head, count, 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self.head:
            yield self.head
        for _ in range(self.count):
            self.pulled += 1
            yield b"x"


@pytest.mark.parametrize(
    ("coding", "member"),
    [
        ("gzip", gzip.compress(ICS, mtime=0)),
        ("deflate", zlib.compress(ICS)),
        ("deflate", raw_deflate(ICS)),
    ],
    ids=["gzip", "deflate", "raw-deflate"],
)
async def test_nothing_after_the_end_of_the_compressed_body_is_read(
    coding: str, member: bytes
) -> None:
    # Read on, junk in one-byte pieces made the decoder copy all it had put aside again for
    # each piece: 400 KB of it held the event loop for 2.7 s.
    body = Drip(member, 50_000)
    assert await fetcher(coded(body, coding)).fetch("https://uni.example/a") == ICS
    assert body.pulled == 0


async def test_a_body_in_more_pieces_than_any_server_sends_is_refused() -> None:
    # A 2 MB calendar arrives in about 1 500 network reads even over a slow link; every read
    # costs the event loop, so a server that drips its body a byte at a time is cut off.
    exact = Drip(b"", MOST_PIECES)
    assert await fetcher(coded(exact)).fetch("https://uni.example/a") == b"x" * MOST_PIECES
    more = Drip(b"", MOST_PIECES + 1)
    assert await reason(fetcher(coded(more)).fetch("https://uni.example/a")) == "unreachable"
    assert more.pulled == MOST_PIECES + 1


async def test_a_damaged_gzip_body_is_unreachable() -> None:
    calendars = fetcher(coded(Body(b"not gzip at all"), "gzip"))
    assert await reason(calendars.fetch("https://uni.example/a")) == "unreachable"


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


@pytest.mark.parametrize(
    "host",
    ["a..b", ".uni.example", "a" * 64 + ".example"],
    ids=["double-dot", "leading-dot", "64-character-label"],
)
async def test_a_name_the_resolver_cannot_encode_is_unreachable(host: str) -> None:
    calls: list[httpx.Request] = []
    handler = lambda request: calls.append(request) or httpx.Response(200)  # noqa: E731
    # The real resolver: Python IDNA-encodes the name and refuses an empty or 64-character
    # label with UnicodeError before any lookup.
    calendars = CalendarFetcher(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await reason(calendars.fetch(f"https://{host}/cal.ics")) == "unreachable"
    assert calls == []


async def test_a_name_that_does_not_decode_is_unreachable() -> None:
    # "xn--a" is ASCII but no IDNA name: httpx's URL.host decodes it and raises.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/hop":
            return httpx.Response(302, headers={"Location": "https://xn--a/cal.ics"})
        return httpx.Response(200, content=ICS)

    calendars = fetcher(handler)
    assert await reason(calendars.fetch("https://xn--a/cal.ics")) == "unreachable"
    assert await reason(calendars.fetch("https://uni.example/hop")) == "unreachable"


async def test_a_slow_server_is_unreachable() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, content=ICS)

    got = await reason(fetcher(slow, timeout=0.05).fetch("https://uni.example/a"))
    assert got == "unreachable"


async def test_the_calendar_client_shares_no_cookies_and_waits_ten_seconds() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"Set-Cookie": "planted=1; Path=/"}, stream=Body(ICS))

    http = calendar_client()
    http._transport = httpx.MockTransport(handler)  # the client as built, minus the network
    # Two sites behind one address: what one of them sets must not reach the other.
    table = {"uni.example": [PUBLIC], "other.example": [PUBLIC]}
    calendars = CalendarFetcher(http, resolver(table))
    try:
        assert await calendars.fetch("https://uni.example/a.ics") == ICS
        assert await calendars.fetch("https://other.example/b.ics") == ICS
    finally:
        await http.aclose()
    assert [request.headers.get("cookie") for request in seen] == [None, None]
    assert not http.cookies and http.trust_env is False
    # Each phase gets the whole TIMEOUT; the fetcher's own deadline bounds the download.
    phases = ("connect", "read", "write", "pool")
    assert seen[1].extensions["timeout"] == dict.fromkeys(phases, 10.0)


def test_normalize_and_public_helpers() -> None:
    assert str(normalize(" WEBCAL://uni.example/a.ics ")) == "https://uni.example/a.ics"
    assert is_public(PUBLIC) and not is_public("192.168.1.1") and not is_public("::ffff:127.0.0.1")


def test_6to4_and_teredo_are_refused_whatever_python_thinks_of_them(monkeypatch) -> None:
    # Not every Python release counts these tunnel prefixes as non-global; the check does not
    # rely on its verdict.
    monkeypatch.setattr(ipaddress.IPv6Address, "is_global", property(lambda self: True))
    assert not is_public("2002:a00:1::1")
    assert not is_public("2001:0:4136:e378:8000:63bf:3fff:fdd2")
    assert is_public("2001:4860:4860::8888")
