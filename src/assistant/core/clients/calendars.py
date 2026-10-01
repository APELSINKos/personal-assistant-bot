"""Downloading a calendar someone pasted a link to — without letting the link reach inside.

Only https on port 443. The host is resolved here and every address must be public; the
request then goes to that very address (the name travels in Host and SNI, so TLS still checks
the certificate), which closes the window between the check and the connection. Redirects are
followed by hand, up to three, each checked the same way.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
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

Resolver = Callable[[str, int], Awaitable[list[str]]]


class Calendars(Protocol):
    """What the schedule code needs from a downloader: CalendarFetcher, or a stub in tests."""

    async def fetch(self, url: str) -> bytes: ...

    async def head(self, url: str, limit: int = 4096) -> bytes: ...


def _refused(reason: str) -> InvalidInput:
    return InvalidInput(field="url", reason=reason)


async def resolve_host(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
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
        or not parsed.host
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

    async def _address(self, url: httpx.URL) -> str:
        try:
            literal: str | None = str(ipaddress.ip_address(url.host))
        except ValueError:
            literal = None
        if literal is not None:
            addresses = [literal]
        else:
            try:
                addresses = await self._resolve(url.host, 443)
            except OSError as error:
                raise _refused("unreachable") from error
        if not addresses or not all(is_public(address) for address in addresses):
            raise _refused("forbidden_host")
        ipv4 = [a for a in addresses if ipaddress.ip_address(a).version == 4]
        return (ipv4 or addresses)[0]

    async def _download(self, url: str, limit: int, strict_size: bool) -> bytes:
        current = normalize(url)
        for _ in range(MAX_REDIRECTS + 1):
            address = await self._address(current)
            request = self._http.build_request(
                "GET",
                current.copy_with(host=address),
                headers={
                    "Host": current.host,
                    "User-Agent": USER_AGENT,
                    "Accept": "text/calendar, */*;q=0.5",
                },
                extensions={"sni_hostname": current.host},
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
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > limit:
                        if strict_size:
                            raise _refused("too_large")
                        return bytes(body[:limit])
                return bytes(body)
            finally:
                await response.aclose()
        raise _refused("unreachable")

    async def _run(self, url: str, limit: int, strict_size: bool) -> bytes:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._download(url, limit, strict_size)
        except (httpx.HTTPError, TimeoutError, OSError) as error:
            raise _refused("unreachable") from error

    async def fetch(self, url: str) -> bytes:
        """The whole calendar, at most `max_bytes`; InvalidInput(field="url", reason=…) with
        reason forbidden_host, unreachable or too_large otherwise."""
        return await self._run(url, self._max_bytes, strict_size=True)

    async def head(self, url: str, limit: int = 4096) -> bytes:
        """Only the first `limit` bytes (the calendar's header); the rest is never read."""
        return await self._run(url, limit, strict_size=False)
