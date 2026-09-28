"""Logging to stdout (journald on the server) with secrets removed from every record."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable

_TOKEN_IN_URL = re.compile(r"bot\d{6,}:[A-Za-z0-9_-]+")


class TokenRedactor(logging.Filter):
    """Removes known secrets and anything shaped like a bot token from messages and tracebacks."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def _clean(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return _TOKEN_IN_URL.sub("bot***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._clean(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = self._clean(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self._clean(record.exc_text)
        return True


def setup_logging(level: str, secrets: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(TokenRedactor(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
