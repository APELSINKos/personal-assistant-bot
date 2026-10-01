"""Downloading a calendar someone pasted a link to — without letting the link reach inside.

Only https on port 443. The host is resolved here and every address must be public; the
request then goes to that very address (the name travels in Host and SNI, so TLS still checks
the certificate), which closes the window between the check and the connection. Redirects are
followed by hand, up to three, each checked the same way. The body is read raw and asked for
without any content coding; one gzip or deflate layer a server sends anyway is undone here,
under the same size limit, and anything else is refused.

Every failure, too_large included, is InvalidInput(field="url", reason=…): the user gave a link.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import zlib
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from assistant.core.errors import InvalidInput

USER_AGENT = (
    "personal-assistant-bot schedule (+https://github.com/APELSINKos/personal-assistant-bot)"
)
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
URL_LENGTH = 2000
TIMEOUT = 10.0  # seconds for the whole download, redirects included
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
# Raw bytes allowed past the limit. Compressed data never runs much longer than what it decodes
# to; beyond this it is padding the decoder only sits on (gzip header fields, empty blocks,
# junk after the end).
_RAW_EXTRA = 64 * 1024
# IPv6 forms that carry an IPv4 address in their last 32 bits: IPv4-mapped, IPv4-compatible,
# IPv4-translated and NAT64's well-known prefix. That IPv4 is where the packet ends up (under
# DNS64 an A record pointing inside comes back as 64:ff9b::10.x), so it is the one judged.
# :: and ::1 fall in ::/96 too and stay refused: they carry 0.0.0.0 and 0.0.0.1.
_CARRY_IPV4 = tuple(
    ipaddress.IPv6Network(network)
    for network in ("::ffff:0:0/96", "::/96", "::ffff:0:0:0/96", "64:ff9b::/96")
)

Resolver = Callable[[str, int], Awaitable[list[str]]]


class Calendars(Protocol):
    """What the schedule code needs from a downloader: CalendarFetcher, or a stub in tests."""

    async def fetch(self, url: str) -> bytes: ...

    async def head(self, url: str, limit: int = 4096) -> bytes: ...


def _refused(reason: str) -> InvalidInput:
    return InvalidInput(field="url", reason=reason)


class _Decoder(Protocol):
    def decompress(self, data: bytes, max_length: int, /) -> bytes: ...


class _Identity:
    def decompress(self, data: bytes, max_length: int, /) -> bytes:
        return data[:max_length]


class _Deflate:
    """deflate as servers send it: zlib-wrapped, as the RFC means it, or bare, as some still
    do. Like httpx, the bare form is tried when the first chunk does not read as zlib."""

    def __init__(self) -> None:
        self._inflate = zlib.decompressobj()
        self._first = True

    def decompress(self, data: bytes, max_length: int, /) -> bytes:
        first, self._first = self._first, False
        try:
            return self._inflate.decompress(data, max_length)
        except zlib.error:
            if not first:
                raise
            self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)
            return self._inflate.decompress(data, max_length)


def _decoder(headers: httpx.Headers) -> _Decoder:
    """What undoes the body's content coding: nothing, or one gzip or deflate layer.

    Anything else is refused before a byte is read: every extra layer multiplies what a few
    bytes expand to (two gzip layers make 128 MiB of 400 bytes), and httpx would decode each
    without a limit."""
    codings = [
        coding
        for value in headers.get_list("content-encoding", split_commas=True)
        if (coding := value.lower()) not in ("", "identity")
    ]
    if not codings:
        return _Identity()
    if codings in (["gzip"], ["x-gzip"]):
        return zlib.decompressobj(zlib.MAX_WBITS | 16)
    if codings == ["deflate"]:
        return _Deflate()
    raise _refused("unreachable")


async def resolve_host(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:
            return False  # fec0::/10, deprecated, yet is_global still says yes
        if any(ip in network for network in _CARRY_IPV4):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    # is_global is false for private, loopback, link-local (cloud metadata), CGNAT, reserved.
    return ip.is_global


def normalize(url: str) -> httpx.URL:
    """The link as it will be fetched: webcal:// becomes https://; anything else is refused."""
    text = url.strip()
    if len(text) > URL_LENGTH:
        raise _refused("forbidden_host")
    if text.lower().startswith("webcal://"):
        text = "https://" + text[len("webcal://") :]
    try:
        parsed = httpx.URL(text)
    except (httpx.InvalidURL, ValueError) as error:
        raise _refused("forbidden_host") from error
    if (
        parsed.scheme != "https"
        or not parsed.raw_host  # .host would IDNA-decode, and raise on «xn--» junk
        or parsed.userinfo
        or parsed.port not in (None, 443)
    ):
        raise _refused("forbidden_host")
    return parsed


class CalendarFetcher:
    def __init__(
        self,
        http: httpx.AsyncClient,
        resolve: Resolver = resolve_host,
        *,
        max_bytes: int = MAX_BYTES,
        timeout: float = TIMEOUT,
    ) -> None:
        self._http = http
        self._resolve = resolve
        self._max_bytes = max_bytes
        self._timeout = timeout

    async def _address(self, host: str) -> str:
        try:
            literal: str | None = str(ipaddress.ip_address(host))
        except ValueError:
            literal = None
        if literal is not None:
            addresses = [literal]
        else:
            try:
                addresses = await self._resolve(host, 443)
            except (OSError, ValueError) as error:
                # The system resolver IDNA-encodes the name before any lookup and refuses an
                # empty or 64-character label with UnicodeError, a ValueError.
                raise _refused("unreachable") from error
        if not addresses or not all(is_public(address) for address in addresses):
            raise _refused("forbidden_host")
        ipv4 = [a for a in addresses if ipaddress.ip_address(a).version == 4]
        return (ipv4 or addresses)[0]

    async def _download(self, url: str, limit: int, strict_size: bool) -> bytes:
        current = normalize(url)
        for _ in range(MAX_REDIRECTS + 1):
            # Only ASCII forms go out: a Unicode name as httpx's own IDNA 2008 A-labels (header
            # values must be ASCII), an IPv6 literal in brackets in Host.
            host = current.raw_host.decode("ascii")
            address = await self._address(host)
            request = self._http.build_request(
                "GET",
                current.copy_with(host=address),
                headers={
                    "Host": current.netloc.decode("ascii"),
                    "User-Agent": USER_AGENT,
                    "Accept": "text/calendar, */*;q=0.5",
                    # httpx would ask for gzip and undo any stack of layers without a limit
                    "Accept-Encoding": "identity",
                },
                extensions={"sni_hostname": host},
            )
            response = await self._http.send(request, stream=True, follow_redirects=False)
            try:
                if response.status_code in _REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        raise _refused("unreachable")
                    current = normalize(str(current.join(location)))
                    continue
                if response.status_code != 200:
                    raise _refused("unreachable")
                return await self._read(response, limit, strict_size)
            finally:
                await response.aclose()
        raise _refused("unreachable")

    async def _read(self, response: httpx.Response, limit: int, strict_size: bool) -> bytes:
        """At most `limit` decoded bytes; past it, too_large (fetch) or the cut (head)."""
        decoder = _decoder(response.headers)
        body = bytearray()
        received = 0
        async for chunk in response.aiter_raw():
            received += len(chunk)
            # max_length bounds what one chunk may expand to, so a bomb stops at limit + 1
            # bytes. It is never 0 here, which zlib would take as «no limit».
            body += decoder.decompress(chunk, limit + 1 - len(body))
            if len(body) > limit or received > limit + _RAW_EXTRA:
                if strict_size:
                    raise _refused("too_large")
                return bytes(body[:limit])
        return bytes(body)

    async def _run(self, url: str, limit: int, strict_size: bool) -> bytes:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._download(url, limit, strict_size)
        except (
            httpx.HTTPError,
            httpx.InvalidURL,
            TimeoutError,
            OSError,
            UnicodeError,
            zlib.error,
        ) as error:
            # httpx prepares the next hop of a redirect even when it is not asked to follow it:
            # it IDNA-decodes the target (UnicodeError) and gives a hostless one our host, which
            # its own URL check may refuse (InvalidURL). zlib.error: a damaged gzip or deflate body.
            raise _refused("unreachable") from error

    async def fetch(self, url: str) -> bytes:
        """The whole calendar, at most `max_bytes`; InvalidInput(field="url", reason=…) with
        reason forbidden_host, unreachable or too_large otherwise."""
        return await self._run(url, self._max_bytes, strict_size=True)

    async def head(self, url: str, limit: int = 4096) -> bytes:
        """Only the first `limit` bytes (the calendar's header); the rest is never read."""
        return await self._run(url, limit, strict_size=False)
