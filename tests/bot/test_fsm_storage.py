from __future__ import annotations

from aiogram.fsm.storage.base import StorageKey

from assistant.bot.fsm_storage import SqliteStorage


async def test_state_and_data_survive_a_new_storage(sessionmaker) -> None:
    key = StorageKey(bot_id=1, chat_id=10, user_id=10)
    first = SqliteStorage(sessionmaker)
    await first.set_state(key, "NoteForm:text")
    await first.set_data(key, {"hint": "hint-note", "n": 1})
    second = SqliteStorage(sessionmaker)
    assert await second.get_state(key) == "NoteForm:text"
    assert await second.get_data(key) == {"hint": "hint-note", "n": 1}
    await second.set_state(key, None)
    await second.set_data(key, {})
    assert await second.get_state(key) is None
    assert await second.get_data(key) == {}


async def test_missing_key_is_empty(sessionmaker) -> None:
    storage = SqliteStorage(sessionmaker)
    key = StorageKey(bot_id=1, chat_id=5, user_id=5)
    assert await storage.get_state(key) is None
    assert await storage.get_data(key) == {}
