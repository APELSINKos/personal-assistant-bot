"""Rich messages never reach aiogram's validation (aiogram issue #1925)."""

from __future__ import annotations

import json
import time
from typing import Any

from aiogram.methods import GetUpdates

from assistant.bot.app import create_bot, drop_rich_messages
from assistant.core.config import Settings

KINDS = ("bold", "italic", "underline", "strikethrough")


def nested(depth: int) -> Any:
    text: Any = "x"
    for level in range(depth):
        text = {"type": KINDS[level % len(KINDS)], "text": text}
    return text


def updates(depth: int) -> str:
    rich = {"blocks": [{"type": "paragraph", "text": nested(depth)}]}
    chat = {"id": 1, "type": "private"}
    message = {
        "message_id": 7,
        "date": 0,
        "chat": chat,
        "from": {"id": 1, "is_bot": False, "first_name": "Alex"},
        "rich_message": rich,
        "reply_to_message": {"message_id": 6, "date": 0, "chat": chat, "rich_message": rich},
    }
    return json.dumps({"ok": True, "result": [{"update_id": 1, "message": message}]})


def test_rich_messages_are_dropped_at_any_depth() -> None:
    data = drop_rich_messages(updates(3))
    message = data["result"][0]["message"]
    assert "rich_message" not in message
    assert "rich_message" not in message["reply_to_message"]
    assert message["message_id"] == 7
    assert message["reply_to_message"]["message_id"] == 6


def test_other_responses_are_decoded_unchanged() -> None:
    result = {"message_id": 3, "text": "rich_message", "entities": [], "x": [1, None]}
    content = json.dumps({"ok": True, "result": result})
    assert drop_rich_messages(content) == json.loads(content)


def test_a_deeply_nested_rich_message_does_not_freeze_polling(settings: Settings) -> None:
    bot = create_bot(settings)
    started = time.perf_counter()
    response = bot.session.check_response(bot, GetUpdates(), 200, updates(5))
    # Validated as it is, this payload (two rich messages, depth 5) takes about 20 s, and
    # every further level about 20 times more.
    assert time.perf_counter() - started < 1
    [update] = response.result
    assert update.message is not None
    assert update.message.rich_message is None
    assert update.message.text is None
