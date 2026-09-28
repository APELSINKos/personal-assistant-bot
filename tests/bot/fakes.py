"""A fake aiogram session that records API calls instead of sending them."""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

_ids = itertools.count(1000)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.errors: list[BaseException] = []  # raised one per call, oldest first
        self.results: dict[type[Any], Any] = {}

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        # ASYNC109 is suppressed above: this overrides BaseSession.make_request, whose
        # signature (including `timeout`) is fixed by aiogram and cannot be changed.
        self.calls.append(method)
        if self.errors:
            raise self.errors.pop(0)
        if type(method) in self.results:
            return self.results[type(method)]
        if isinstance(method, SendMessage | EditMessageText):
            return Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id or 1), type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        return None

    def sent_texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, SendMessage | EditMessageText)]

    def of(self, kind: type[Any]) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind)]


def tg_user(user_id: int = 1, lang: str = "ru") -> User:
    return User(id=user_id, is_bot=False, first_name="Alex", language_code=lang)


def message_update(
    text: str | None = None,
    *,
    user_id: int = 1,
    lang: str = "ru",
    chat_type: str = "private",
    sticker: bool = False,
) -> Update:
    extra: dict[str, Any] = {}
    if sticker:
        extra["sticker"] = {
            "file_id": "x",
            "file_unique_id": "y",
            "type": "regular",
            "width": 1,
            "height": 1,
            "is_animated": False,
            "is_video": False,
        }
    chat = Chat(id=user_id if chat_type == "private" else -100, type=chat_type)
    msg = Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=chat,
        from_user=tg_user(user_id, lang),
        text=text,
        **extra,
    )
    return Update(update_id=next(_ids), message=msg)


def callback_update(data: str, *, user_id: int = 1, lang: str = "ru") -> Update:
    msg = Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        text="list",
    )
    query = CallbackQuery(
        id=str(next(_ids)),
        from_user=tg_user(user_id, lang),
        chat_instance="ci",
        data=data,
        message=msg,
    )
    return Update(update_id=next(_ids), callback_query=query)
