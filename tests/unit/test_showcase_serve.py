from __future__ import annotations

import http.client
import socket
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from scripts.showcase import serve


@pytest.fixture
def server(tmp_path: Path) -> Iterator[serve.Server]:
    demo, pages, fonts = tmp_path / "dist-demo", tmp_path / "pages", tmp_path / "fonts"
    (demo / "assets").mkdir(parents=True)
    pages.mkdir()
    fonts.mkdir()
    (demo / "index.html").write_text("<!doctype html><title>демо</title>", encoding="utf-8")
    (demo / "assets" / "main.js").write_text("export {};", encoding="utf-8")
    (demo / "assets" / "manrope.woff2").write_bytes(b"wOF2")
    (demo / "notes.txt").write_text("not a type of the site", encoding="utf-8")
    (pages / "week.dark.html").write_text("<p>📅</p>", encoding="utf-8")
    (fonts / "Roboto[wdth,wght].ttf").write_bytes(b"\0\1\0\0")
    (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
    with serve.serve({"/demo/": demo, "/showcase/": pages, "/showcase/fonts/": fonts}) as running:
        yield running


def ask(server: serve.Server, path: str, method: str = "GET") -> tuple[int, str | None, bytes]:
    address = urlsplit(server.origin)
    connection = http.client.HTTPConnection(address.hostname or "", address.port, timeout=5)
    try:
        connection.request(method, path)  # sent as written: no client tidies «..» away
        answer = connection.getresponse()
        return answer.status, answer.getheader("Content-Type"), answer.read()
    finally:
        connection.close()


def test_it_listens_on_the_loopback_only(server: serve.Server) -> None:
    address = urlsplit(server.origin)
    assert (address.scheme, address.hostname) == ("http", "127.0.0.1")
    assert address.port
    assert server.url("/demo/index.html") == f"{server.origin}/demo/index.html"


def test_each_type_comes_from_its_own_table(server: serve.Server) -> None:
    assert ask(server, "/demo/index.html?shot=1&lang=ru#/") == (
        200,
        "text/html; charset=utf-8",
        "<!doctype html><title>демо</title>".encode(),
    )
    assert ask(server, "/demo/")[:2] == (200, "text/html; charset=utf-8")
    assert ask(server, "/demo/assets/main.js")[1] == "text/javascript; charset=utf-8"
    assert ask(server, "/demo/assets/manrope.woff2")[1] == "font/woff2"
    assert ask(server, "/showcase/week.dark.html")[1] == "text/html; charset=utf-8"
    # The longer prefix wins, and a name with brackets is asked for quoted.
    assert ask(server, "/showcase/fonts/Roboto%5Bwdth%2Cwght%5D.ttf")[1:] == (
        "font/ttf",
        b"\0\1\0\0",
    )


def test_a_head_request_gets_the_headers_only(server: serve.Server) -> None:
    assert ask(server, "/demo/assets/main.js", "HEAD") == (
        200,
        "text/javascript; charset=utf-8",
        b"",
    )


@pytest.mark.parametrize(
    "path",
    [
        "/demo/notes.txt",  # a type it does not know
        "/demo/assets",  # a folder
        "/demo/missing.js",
        "/elsewhere/index.html",
        "/demo/../secret.json",
        "/demo/..%2Fsecret.json",
        "/showcase/fonts/..%5C..%5Csecret.json",
    ],
)
def test_nothing_else_is_served(server: serve.Server, path: str) -> None:
    assert ask(server, path)[0] == 404


def test_it_stops_with_its_block(tmp_path: Path) -> None:
    with serve.serve({"/demo/": tmp_path}) as running:
        port = urlsplit(running.origin).port
        with socket.socket() as taken, pytest.raises(OSError):
            taken.bind(("127.0.0.1", port))
    with socket.socket() as free:
        free.bind(("127.0.0.1", port))  # the port is given back
