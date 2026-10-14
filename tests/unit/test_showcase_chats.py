from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn

import pytest
from scripts.showcase import chats, readme, world

from assistant.bot import scheduler
from assistant.bot.routers import money_entry
from assistant.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
LANGS = ("ru", "en")


@pytest.fixture(scope="module")
def recorded() -> dict[str, dict[str, Any]]:
    """The six scenes as the bot plays them now, in both languages: a run each."""
    return {lang: chats.transcript(lang) for lang in LANGS}


def committed(lang: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (IMAGES / readme.TRANSCRIPT[lang]).read_text(encoding="utf-8")
    )
    return data


@pytest.mark.parametrize("lang", LANGS)
def test_the_transcripts_are_what_the_bot_says(
    lang: str, recorded: dict[str, dict[str, Any]]
) -> None:
    # A change to any of the six messages lands here until the pictures are redrawn:
    # uv run python -m scripts.showcase chats (then readme), as for the cards (spec §13.8).
    assert recorded[lang] == committed(lang)


@pytest.mark.parametrize("lang", LANGS)
def test_the_readme_block_is_drawn_from_the_transcript(lang: str) -> None:
    text = (ROOT / readme.README[lang]).read_text(encoding="utf-8")
    assert readme.between(text) == readme.render(committed(lang), lang)


def test_the_scenes_show_the_chat_s_last_state(recorded: dict[str, dict[str, Any]]) -> None:
    scenes = recorded["ru"]
    assert list(scenes) == list(chats.SCENES)
    # The press of «✅ Создать» took the card's buttons and brought a confirmation; the reminder
    # itself came the next morning.
    reminder = scenes["reminder"]["messages"]
    assert [message["from"] for message in reminder] == ["user", "bot", "bot", "bot"]
    assert reminder[0]["text"] == "по будням в 7:30 зарядка"
    assert reminder[1]["inline"] == []
    assert reminder[3]["at"] == "2026-10-08T07:30"
    # The list of notes became the card of «Покупки», and «хлеб» is ticked on it.
    checklist = scenes["checklist"]["messages"]
    assert len(checklist) == 2
    assert "✅ хлеб" in checklist[1]["text"].splitlines()
    # The menu stands in the chat since /start, and only the habits' picture shows it.
    assert [name for name, scene in scenes.items() if "menu" in scene] == ["habits"]
    assert scenes["habits"]["menu"][0] == ["🌤 Погода", "📅 Мой день"]
    # The evening's reminder went at 19:00, outside the pictures.
    texts = [message["text"] for scene in scenes.values() for message in scene["messages"]]
    assert not any("тренировка" in text and "⏰" in text for text in texts)


def _broken(*args: object, **kwargs: object) -> NoReturn:
    raise ValueError("a bug")


# What can fail in a scene, and what the run says when it stops.
FAILURES: dict[str, tuple[object, str, object, str]] = {
    # A handler that raises: the bot's error router would answer with its apology.
    "handler": (money_entry, "entry_text", _broken, r"ValueError\('a bug'\)"),
    # A method the chat cannot show, as if a scene had started to use a new one.
    "method": (chats, "EditMessageReplyMarkup", type("New", (), {}), "EditMessageReplyMarkup"),
    # The scheduler logs a failure and goes on: the scene would be short of its message.
    "digest": (scheduler.texts, "morning_text", _broken, "the scheduler sent 0 messages"),
    "reminder": (scheduler, "reminder_text", _broken, "the scheduler sent 0 messages"),
}


@pytest.mark.parametrize("failure", FAILURES)
def test_a_scene_that_fails_stops_the_run(failure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Else the generator would draw the apology, or a scene without its message, and the test of
    # the transcripts would agree: the bot really says that then.
    module, name, broken, said = FAILURES[failure]
    monkeypatch.setattr(module, name, broken)
    with pytest.raises(RuntimeError, match=f"a scene failed: .*{said}"):
        chats.transcript("ru")


@pytest.mark.parametrize("lang", LANGS)
def test_no_address_reaches_a_transcript(lang: str) -> None:
    assert chats.strangers(committed(lang)) == []


def test_the_guard_lets_only_the_sources_of_the_data_through() -> None:
    allowed = "Погода — open-meteo.com, города — https://www.geonames.org/about.html"
    assert chats.strangers({"week": {"messages": [{"text": allowed, "inline": []}]}}) == []
    words = "the chat.messages, about.me"  # no address in them
    assert chats.strangers({"week": {"messages": [{"text": words, "inline": []}]}}) == []
    found = chats.strangers(
        {
            "morning": {
                "messages": [
                    {"text": "открой http://192.0.2.7:8080/app", "inline": []},
                    {"text": "ok", "inline": [["бот", "t.me/some_bot"]]},
                ]
            },
            "habits": {"messages": [], "menu": [["https://example.com"]]},
        }
    )
    assert found == [
        "morning: http://192.0.2.7:8080/app",
        "morning: t.me/some_bot",
        "habits: https://example.com",
    ]
    with pytest.raises(ValueError, match="t.me/some_bot"):
        chats.check({"x": {"messages": [{"text": "t.me/some_bot", "inline": []}]}})


def test_the_world_sets_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    # Neither .env nor the developer's shell changes the transcripts: every field is given, and
    # an argument wins over the environment.
    assert world.settings().model_fields_set == set(Settings.model_fields)
    monkeypatch.setenv("DEFAULT_CITY", "Тула")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com/app")
    settings = world.settings()
    assert (settings.default_city, settings.webapp_url) == ("Москва", None)
    assert settings.bot_token.get_secret_value() == "123456:SHOWCASE"


def test_a_transcript_is_written_with_the_invisible_characters_escaped() -> None:
    text = chats.dump({"money": {"messages": [{"text": "23\u00a0850\u00a0₽ ☀\ufe0f"}]}})
    assert "23\\u00a0850\\u00a0₽ ☀\\ufe0f" in text
    assert json.loads(text) == {"money": {"messages": [{"text": "23\u00a0850\u00a0₽ ☀\ufe0f"}]}}
    assert text.endswith("}\n")
