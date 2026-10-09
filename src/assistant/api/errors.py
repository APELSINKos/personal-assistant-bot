"""Every error leaves the API as application/problem+json; internals never do."""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from assistant.api.auth import AuthError
from assistant.core.errors import (
    InvalidInput,
    LimitReached,
    NotFound,
    ServiceError,
    UpstreamUnavailable,
    WriteForbidden,
)

log = logging.getLogger(__name__)
PROBLEM = "application/problem+json"
_SERVICE: dict[type[ServiceError], tuple[int, str, str]] = {
    InvalidInput: (422, "validation_error", "Invalid input"),
    LimitReached: (409, "limit_reached", "Limit reached"),
    NotFound: (404, "not_found", "Not found"),
    UpstreamUnavailable: (503, "upstream_unavailable", "Upstream service unavailable"),
    WriteForbidden: (403, "write_forbidden", "The bot may not write to the user"),
}


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__("rate_limited")
        self.retry_after = retry_after


def _plain(value: object) -> object:
    return value if isinstance(value, str | int | float | bool) else str(value)


def problem(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **params: Any,
) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status, "code": code}
    if detail:
        body["detail"] = detail
    body.update({key: _plain(value) for key, value in params.items() if value is not None})
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


async def _service_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ServiceError)
    status, code, title = _SERVICE.get(type(error), (400, error.code, "Request failed"))
    params: dict[str, Any] = error.params
    return problem(status, code, title, **params)


async def _auth_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AuthError)
    return problem(401, error.code, "Unauthorized", headers={"WWW-Authenticate": "tma"})


async def _rate_limited(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RateLimited)
    wait = max(1, math.ceil(error.retry_after))
    return problem(429, "rate_limited", "Too many requests", headers={"Retry-After": str(wait)})


_LIMIT_KEYS = ("min_length", "max_length", "ge", "gt", "le", "lt")


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    first = error.errors()[0] if error.errors() else {}
    location = [str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path")]
    ctx = first.get("ctx") or {}
    limit = next((ctx[key] for key in _LIMIT_KEYS if key in ctx), None)
    return problem(
        422,
        "validation_error",
        "Invalid input",
        detail=first.get("msg"),
        field=".".join(location) or None,
        limit=limit,
    )


async def _http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = "not_found" if error.status_code == 404 else "http_error"
    headers = dict(error.headers) if error.headers else None
    return problem(error.status_code, code, str(error.detail), headers=headers)


async def _internal_error(request: Request, error: Exception) -> JSONResponse:
    # One line only: Starlette re-raises the error afterwards and the server logs its traceback.
    log.error("request %s %s failed", request.method, request.url.path)
    return problem(500, "internal_error", "Internal server error")


def install(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error)
    app.add_exception_handler(AuthError, _auth_error)
    app.add_exception_handler(RateLimited, _rate_limited)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _internal_error)
