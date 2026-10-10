"""Domain errors raised by services and translated to messages by the adapters."""

from __future__ import annotations


class ServiceError(Exception):
    code = "error"

    def __init__(self, **params: object) -> None:
        super().__init__(self.code)
        self.params: dict[str, object] = params


class InvalidInput(ServiceError):
    code = "invalid_input"


class LimitReached(ServiceError):
    code = "limit_reached"


class NotFound(ServiceError):
    code = "not_found"


class UpstreamUnavailable(ServiceError):
    code = "upstream_unavailable"


class WriteForbidden(ServiceError):
    """Telegram does not let the bot write to the user: blocked, or never started."""

    code = "write_forbidden"
