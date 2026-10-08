"""Logging to stdout (journald on the server, every line with its priority) with secrets removed
from every record."""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Iterable
from typing import TextIO

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


class JournalFormatter(logging.Formatter):
    """Starts every line of a record with its syslog priority. journald reads one at the start
    of each line it gets (SyslogLevelPrefix=), so the lines of a traceback need it too."""

    def format(self, record: logging.LogRecord) -> str:
        prefix = f"<{_priority(record.levelno)}>"
        return "\n".join(prefix + line for line in super().format(record).split("\n"))


def _priority(level: int) -> int:
    if level >= logging.ERROR:
        return 3  # err
    if level >= logging.WARNING:
        return 4  # warning
    if level >= logging.INFO:
        return 6  # info
    return 7  # debug


def _to_journal(stream: TextIO) -> bool:
    """Whether the stream is the service's connection to journald. systemd gives its device and
    inode in JOURNAL_STREAM; a process that inherited the variable but writes elsewhere does not
    match them."""
    journal = os.environ.get("JOURNAL_STREAM")
    if not journal:
        return False
    try:
        stat = os.fstat(stream.fileno())
    except (OSError, ValueError):  # not backed by a file descriptor, or closed
        return False
    return journal == f"{stat.st_dev}:{stat.st_ino}"


def setup_logging(level: str, secrets: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = JournalFormatter if _to_journal(sys.stdout) else logging.Formatter
    handler.setFormatter(formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(TokenRedactor(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Their INFO lines carry request URLs, i.e. the city names people type and coordinates.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
