"""The run's own web server (spec §13.1): the demo's build and the generator's chat pages and
fonts for the browser, from one origin on 127.0.0.1 and a free port, and nothing else.

A file's type comes from the table below, not from mimetypes: Python on Windows knows no .woff2,
.ttf or .webp and takes the type of .js from the registry, where it may be text/plain; the
browser then runs no module, and the demo stays empty.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".json": "application/json",
}


@dataclass(frozen=True)
class Server:
    origin: str  # «http://127.0.0.1:PORT»

    def url(self, path: str) -> str:
        return self.origin + path


def find(routes: list[tuple[str, Path]], target: str) -> Path | None:
    """The file a request asks for: under the folder of the longest prefix of its path, of a
    type in the table, and never outside that folder."""
    path = unquote(urlsplit(target).path)
    for prefix, folder in routes:
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix) :]
        if rest == "" or rest.endswith("/"):
            rest += "index.html"
        try:
            file = (folder / rest).resolve()
            if file.is_relative_to(folder) and file.suffix in TYPES and file.is_file():
                return file
        except (OSError, ValueError):
            pass  # a name no file can have
        return None
    return None


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, routes: list[tuple[str, Path]]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.routes = routes


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:
        self._answer(body=True)

    def do_HEAD(self) -> None:
        self._answer(body=False)

    def _answer(self, body: bool) -> None:
        file = find(self.server.routes, self.path)
        if file is None:
            self.send_error(404)
            return
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES[file.suffix])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if body:
            self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # the run says what it does itself


@contextmanager
def serve(routes: Mapping[str, Path]) -> Iterator[Server]:
    """Serves each folder at its prefix («/demo/» → webapp/dist-demo) while the block runs."""
    ordered = sorted(
        ((prefix, folder.resolve()) for prefix, folder in routes.items()),
        key=lambda route: len(route[0]),
        reverse=True,
    )
    server = _Server(ordered)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="showcase", daemon=True
    )
    thread.start()
    try:
        yield Server(f"http://127.0.0.1:{server.server_address[1]}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
