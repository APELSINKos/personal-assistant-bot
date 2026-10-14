"""The bot's messages in the README, recorded from the bot's own code (spec §13.6): its dispatcher,
handlers, scheduler and texts answer made-up updates in the world of world.py, and a recording
session keeps what the user's chat would show instead of sending anything.

Six scenes: the morning digest; the week under it; a reminder from a phrase, confirmed, and its
first firing the next morning; «кофе 250»; the habits; the shopping list with an item ticked. An
edit changes its message in place, buttons alone included, so a picture shows the chat's last
state. The run starts with /start, in no picture: its welcome brings the menu, which the chat
keeps, as Telegram does, and the habits' scene shows.

A transcript keeps only what a chat shows: who wrote, when, the text and the labels of the buttons,
row by row — never a button's data, an address or a web app — and the guard below refuses any
link but the sources of the data. Nothing goes to the network: Open-Meteo, the bank and the
calendars are the world's. No browser either; aiogram brings aiohttp along by itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import re
import tempfile
import unicodedata
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.bot.app import build_dispatcher
from assistant.bot.db_commit import install_commit_before_request
from assistant.bot.routers import (
    fallback,
    habits,
    money,
    money_entry,
    notes,
    reminders,
    schedule,
    today,
    weather,
)
from assistant.bot.scheduler import Scheduler
from assistant.core.config import Settings
from assistant.core.db import create_engine, make_sessionmaker
from assistant.core.i18n import translator
from assistant.core.models import Base
from assistant.core.services import users
from assistant.core.services.card_kit import card_limiter
from assistant.core.services.schedule import attempt_limiter
from scripts.showcase import world

SCENES = ("morning", "week", "reminder", "money", "habits", "checklist")
# The routers whose module clock the scenes move: every one that has a clock.
CLOCKED = (fallback, habits, money, money_entry, notes, reminders, schedule, today, weather)
# What the user writes besides the menu's buttons.
PHRASES = {
    "ru": {"reminder": "по будням в 7:30 зарядка", "money": "кофе 250"},
    "en": {"reminder": "on weekdays at 7:30 workout", "money": "coffee 250"},
}
# The only hosts a transcript may name: the sources of the data, as /start and /help name them.
SOURCES = ("open-meteo.com", "geonames.org", "creativecommons.org")
_LINK = re.compile(r"[a-z][a-z0-9+.-]*://([^/\s?#]+)\S*|\bt\.me\b\S*", re.IGNORECASE)
# Characters that show nothing of their own, written as escapes in the transcripts' files.
_UNSEEN = frozenset({"Cc", "Cf", "Mn", "Me", "Zs", "Zl", "Zp", "Co", "Cn"})


@dataclass
class Shown:
    """A message as the chat shows it now."""

    sender: str  # "user" or "bot"
    at: datetime
    text: str
    buttons: list[list[InlineKeyboardButton]]


class Recording(BaseSession):
    """The chat with the bot as the user's Telegram shows it: the bot's messages with their latest
    text and buttons, the user's own, and the menu the bot sent last. Sends and edits answer as
    Telegram does, a pressed button's answer is a toast over the chat, and anything else the
    bot asks for stops the run: no transcript could show it."""

    def __init__(self, person: User, clock: Callable[[], datetime]) -> None:
        super().__init__()
        self.person, self.clock = person, clock
        self.scene: str | None = None  # where the next messages go; None: into no picture
        self.messages: dict[int, Shown] = {}
        self.scenes: dict[str, list[int]] = {scene: [] for scene in SCENES}
        self.menu: list[list[str]] = []
        self.menus: dict[str, list[list[str]]] = {}
        self.last = 0  # the bot's latest message
        self._numbers = itertools.count(100)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 (aiogram's signature)
    ) -> Any:
        if isinstance(method, SendMessage):
            self.last = self._add("bot", method.text, method.reply_markup)
            return self._message(self.last)
        if isinstance(method, EditMessageText):
            shown = self.messages[_number(method.message_id)]
            shown.text, shown.buttons = method.text, _inline(method.reply_markup)
            return self._message(_number(method.message_id))
        if isinstance(method, EditMessageReplyMarkup):
            self.messages[_number(method.message_id)].buttons = _inline(method.reply_markup)
            return True
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise RuntimeError(f"the bot asked for {type(method).__name__}, which no chat shows")

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        return None

    def _add(self, sender: str, text: str, markup: object) -> int:
        number = next(self._numbers)
        if isinstance(markup, ReplyKeyboardMarkup):
            self.menu = [[key.text for key in row] for row in markup.keyboard]
        elif isinstance(markup, ReplyKeyboardRemove):
            self.menu = []
        self.messages[number] = Shown(sender, self.clock(), text, _inline(markup))
        if self.scene is not None:
            self.scenes[self.scene].append(number)
        return number

    def _message(self, number: int) -> Message:
        shown = self.messages[number]
        chat = Chat(id=self.person.id, type="private")
        return Message(message_id=number, date=shown.at, chat=chat, text=shown.text)

    def says(self, text: str) -> Update:
        """The user's message, in the chat and as the update the bot gets."""
        number = self._add("user", text, None)
        message = self._message(number).model_copy(update={"from_user": self.person})
        return Update(update_id=number, message=message)

    def presses(self, number: int, label: str) -> Update:
        """A press of the one button under the message whose label holds `label`."""
        found = [button for row in self.messages[number].buttons for button in row]
        found = [button for button in found if label in button.text]
        if len(found) != 1:
            raise LookupError(f"not one button «{label}» under message {number}: {found}")
        query = CallbackQuery(
            id=str(next(self._numbers)),
            from_user=self.person,
            chat_instance="showcase",
            data=found[0].callback_data,
            message=self._message(number),
        )
        return Update(update_id=next(self._numbers), callback_query=query)

    def keep_menu(self) -> None:
        """The menu that stands in the chat at the end of this scene goes into its picture."""
        assert self.scene is not None
        self.menus[self.scene] = self.menu

    def transcript(self) -> dict[str, Any]:
        scenes: dict[str, Any] = {}
        for scene in SCENES:
            messages = [self.messages[number] for number in self.scenes[scene]]
            scenes[scene] = {"messages": [_entry(shown) for shown in messages]}
            if scene in self.menus:
                scenes[scene]["menu"] = self.menus[scene]
        return scenes


def _number(message_id: int | None) -> int:
    assert message_id is not None, "the bot edits the messages of its chat"
    return message_id


def _inline(markup: object) -> list[list[InlineKeyboardButton]]:
    return markup.inline_keyboard if isinstance(markup, InlineKeyboardMarkup) else []


def _entry(shown: Shown) -> dict[str, Any]:
    return {
        "from": shown.sender,
        "at": shown.at.astimezone(world.MOSCOW).strftime("%Y-%m-%dT%H:%M"),
        "text": shown.text,
        "inline": [[button.text for button in row] for row in shown.buttons],
    }


async def record(lang: str) -> dict[str, Any]:
    """The six scenes in `lang`, as the bot plays them now; checked by the guard."""
    with tempfile.TemporaryDirectory(prefix="showcase-chat-", ignore_cleanup_errors=True) as tmp:
        engine = create_engine(f"sqlite+aiosqlite:///{(Path(tmp) / 'chat.db').as_posix()}")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            sessionmaker = make_sessionmaker(engine)
            async with sessionmaker() as session:
                await world.seed(session, lang)
                await session.commit()
            scenes = await _play(sessionmaker, lang)
        finally:
            await engine.dispose()
    check(scenes)
    return scenes


def transcript(lang: str) -> dict[str, Any]:
    """record(), for a caller without an event loop of its own."""
    return asyncio.run(record(lang))


async def _play(sessionmaker: async_sessionmaker[AsyncSession], lang: str) -> dict[str, Any]:
    moment = [world.DIGEST]

    def clock() -> datetime:
        return moment[0].astimezone(UTC)

    person = User(id=world.USER, is_bot=False, first_name=world.NAME[lang], language_code=lang)
    chat = Recording(person, clock)
    settings = world.settings()
    bot = Bot(settings.bot_token.get_secret_value(), session=chat)
    install_commit_before_request(bot)
    meteo, bank = world.Weather(), world.Bank()
    dispatcher = build_dispatcher(
        sessionmaker,
        meteo,  # type: ignore[arg-type]
        bank,  # type: ignore[arg-type]
        settings,
        calendars=world.Calendars(),
        attempts=attempt_limiter(),
        cards=card_limiter(),
    )
    scheduler = Scheduler(bot, sessionmaker, meteo, bank, clock=clock)  # type: ignore[arg-type]
    t = translator(lang)

    async def says(text: str) -> None:
        await dispatcher.feed_update(bot, chat.says(text))

    async def presses(number: int, label: str) -> None:
        await dispatcher.feed_update(bot, chat.presses(number, label))

    with _world_clock(clock, settings):
        await says("/start")
        chat.scene = "morning"
        await scheduler.send_digests(clock())
        digest = chat.last
        chat.scene = "week"
        await presses(digest, t("button-week"))
        moment[0] = world.PHRASES
        chat.scene = "reminder"
        await says(PHRASES[lang]["reminder"])
        await presses(chat.last, t("button-create"))
        chat.scene = "money"
        await says(PHRASES[lang]["money"])
        chat.scene = "habits"
        await says(t("menu-habits"))
        chat.keep_menu()
        chat.scene = "checklist"
        await says(t("menu-notes"))
        listed = chat.last
        title, items = world.SHOPPING[lang]
        await presses(listed, title)
        await presses(listed, items[1])
        moment[0], chat.scene = world.EVENING, None
        await scheduler.deliver_reminders(clock())
        moment[0], chat.scene = world.NEXT_MORNING, "reminder"
        await scheduler.deliver_reminders(clock())
    return chat.transcript()


@contextlib.contextmanager
def _world_clock(clock: Callable[[], datetime], settings: Settings) -> Iterator[None]:
    """The routers' clocks and the settings a new user would get are the world's while the
    scenes play, and the bot's own again after them."""
    kept, settings_of = [router.clock for router in CLOCKED], users.get_settings
    for router in CLOCKED:
        router.clock = clock
    users.get_settings = lambda: settings
    try:
        yield
    finally:
        for router, own in zip(CLOCKED, kept, strict=True):
            router.clock = own
        users.get_settings = settings_of


def _texts(scenes: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Every text a transcript shows, with its scene: messages, buttons, the menu."""
    for name, scene in scenes.items():
        for message in scene["messages"]:
            yield name, message["text"]
            yield from ((name, label) for row in message["inline"] for label in row)
        yield from ((name, key) for row in scene.get("menu", []) for key in row)


def _source(host: str) -> bool:
    host = host.lower().split(":")[0]
    return any(host == source or host.endswith("." + source) for source in SOURCES)


def strangers(scenes: dict[str, Any]) -> list[str]:
    """The links of a transcript to anything but the sources of the data, «scene: link»: an
    address of any scheme, anything of t.me."""
    return [
        f"{name}: {found.group(0)}"
        for name, text in _texts(scenes)
        for found in _LINK.finditer(text)
        if not (found.group(1) and _source(found.group(1)))
    ]


def check(scenes: dict[str, Any]) -> None:
    """The guard of the transcripts: no link but the sources of the data."""
    found = strangers(scenes)
    if found:
        raise ValueError(f"a transcript would show an address: {', '.join(found)}")


def dump(scenes: dict[str, Any]) -> str:
    """A transcript as its file in docs/images/chat holds it: readable JSON, the characters that
    show nothing (a no-break space, the emoji's variation selector) written as escapes."""
    text = json.dumps(scenes, ensure_ascii=False, indent=2) + "\n"
    return "".join(
        json.dumps(char)[1:-1]
        if unicodedata.category(char) in _UNSEEN and not char.isascii()
        else char
        for char in text
    )
