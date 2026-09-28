from __future__ import annotations

import io
import logging

from assistant.core.logging import TokenRedactor

TOKEN = "1234567:AAHabcdefghijklmnopqrstuvwxyz012345"


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
