from __future__ import annotations

import io
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

import pytest

from assistant.core.logging import TokenRedactor, setup_logging

TOKEN = "1234567:AAHabcdefghijklmnopqrstuvwxyz012345"


@pytest.fixture
def stdout(tmp_path: Path) -> Iterator[TextIO]:
    """A file to be the process's stdout; the root logger is restored afterwards. The test puts
    it in place itself: pytest sets its own stdout before every phase of a test."""
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    with (tmp_path / "stdout").open("w+", encoding="utf-8") as stream:
        try:
            yield stream
        finally:
            root.handlers[:] = saved[0]
            root.setLevel(saved[1])


def journal_stream(stream: TextIO) -> str:
    """JOURNAL_STREAM as systemd sets it for a service whose stdout is this stream."""
    stat = os.fstat(stream.fileno())
    return f"{stat.st_dev}:{stat.st_ino}"


def _logger(stream: io.StringIO) -> logging.Logger:
    logger = logging.getLogger("redaction-test")
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(TokenRedactor([TOKEN]))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def test_token_removed_from_message_and_args() -> None:
    stream = io.StringIO()
    _logger(stream).error("failed url https://api.telegram.org/bot%s/sendMessage", TOKEN)
    assert TOKEN not in stream.getvalue()
    assert "bot***" in stream.getvalue()


def test_token_removed_from_traceback() -> None:
    stream = io.StringIO()
    try:
        raise RuntimeError(f"Max retries exceeded with url: /bot{TOKEN}/getUpdates")
    except RuntimeError:
        _logger(stream).exception("polling failed")
    text = stream.getvalue()
    assert "Traceback" in text
    assert TOKEN not in text


def test_unknown_token_shape_is_masked_too() -> None:
    stream = io.StringIO()
    _logger(stream).warning("see /bot987654321:ZZZ-other_token/getMe")
    assert "ZZZ-other_token" not in stream.getvalue()


def test_setup_logging_quiets_http_client_loggers() -> None:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        setup_logging("INFO")
        for name in ("httpx", "httpcore"):
            assert logging.getLogger(name).getEffectiveLevel() == logging.WARNING
            assert not logging.getLogger(name).isEnabledFor(logging.INFO)
        assert logging.getLogger("assistant").isEnabledFor(logging.INFO)
    finally:
        root.handlers[:], _ = saved
        root.setLevel(saved[1])


def test_every_line_in_the_journal_starts_with_its_priority(
    stdout: TextIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOURNAL_STREAM", journal_stream(stdout))
    monkeypatch.setattr(sys, "stdout", stdout)
    setup_logging("DEBUG", [TOKEN])
    log = logging.getLogger("journal-test")
    log.debug("details")
    log.info("Bot started")
    log.warning("slow")
    try:
        raise RuntimeError(f"Max retries exceeded with url: /bot{TOKEN}/getUpdates")
    except RuntimeError:
        log.exception("polling failed")
    log.critical("down")
    stdout.seek(0)
    lines = stdout.read().splitlines()
    assert lines[:3] == [
        "<7>DEBUG journal-test: details",
        "<6>INFO journal-test: Bot started",
        "<4>WARNING journal-test: slow",
    ]
    # journald reads the priority line by line: every line of a traceback carries it, so
    # `journalctl -p err` shows the whole of it. The token is still removed.
    error = lines[3:-1]
    assert error[:2] == [
        "<3>ERROR journal-test: polling failed",
        "<3>Traceback (most recent call last):",
    ]
    assert error[-1] == "<3>RuntimeError: Max retries exceeded with url: /bot***/getUpdates"
    assert all(line.startswith("<3>") for line in error)
    assert lines[-1] == "<3>CRITICAL journal-test: down"


@pytest.mark.parametrize("journal", ["none", "another stream"])
def test_lines_that_do_not_go_to_the_journal_stay_plain(
    stdout: TextIO, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: str
) -> None:
    if journal == "none":  # a terminal
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    else:  # a process that inherited the variable, its output sent elsewhere
        with (tmp_path / "elsewhere").open("w", encoding="utf-8") as elsewhere:
            monkeypatch.setenv("JOURNAL_STREAM", journal_stream(elsewhere))
    monkeypatch.setattr(sys, "stdout", stdout)
    setup_logging("INFO")
    logging.getLogger("journal-test").warning("slow")
    stdout.seek(0)
    assert stdout.read() == "WARNING journal-test: slow\n"
