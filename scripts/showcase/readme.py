"""The «В чате» block of the READMEs (spec §15.4): the six pictures of the bot's messages, two to a
row — the digest and the week, the reminder and the expense, the habits and the list — each a
<picture> of its dark source and its light picture, so it follows GitHub's theme.

A picture's alt text is its chat written out as the README's text blocks used to show it:
«Ты: …» and «Бот: …» where both write (the bot alone just speaks), the buttons in brackets row by
row, a date pill on a line of its own and the habits' menu after the messages. Nothing is lost for
a search or a screen reader. No line of it is blank: a blank line would end the README's HTML.

`uv run python -m scripts.showcase readme` writes the block between the markers from the
transcripts in docs/images/chat, and nobody edits it by hand: tests/unit/test_showcase_chats.py
holds both READMEs to it. Nothing here needs a browser.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from scripts.showcase.chat_page import WIDTH, pill

START = "<!-- chat-pictures: uv run python -m scripts.showcase readme -->"
END = "<!-- /chat-pictures -->"
README = {"ru": "README.md", "en": "README.en.md"}
TRANSCRIPT = {"ru": "chat/chats.json", "en": "chat/chats.en.json"}  # in docs/images
PAIRS = (("morning", "week"), ("reminder", "money"), ("habits", "checklist"))
ORDER = tuple(scene for pair in PAIRS for scene in pair)
WHO = {"ru": {"user": "Ты", "bot": "Бот"}, "en": {"user": "You", "bot": "Bot"}}
MENU = {"ru": "Меню:", "en": "Menu:"}
_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " "})


def picture(scene: str, theme: str, lang: str) -> str:
    """A scene's picture in docs/images: «chat/week.dark.webp», «chat/week.dark.en.webp»."""
    return f"chat/{scene}.{theme}{'' if lang == 'ru' else '.en'}.webp"


def _row(labels: list[str]) -> str:
    return " ".join(f"[{label}]" for label in labels)


def alt(scene: dict[str, Any], lang: str) -> str:
    """The scene's chat as text, line by line."""
    messages = scene["messages"]
    both = any(message["from"] == "user" for message in messages)
    lines: list[str] = []
    for index, message in enumerate(messages):
        if index and messages[index - 1]["at"][:10] != message["at"][:10]:
            lines.append(pill(message["at"], lang))
        text = [line for line in message["text"].translate(_SPACES).split("\n") if line.strip()]
        if both and text:
            text[0] = f"{WHO[lang][message['from']]}: {text[0]}"
        lines += text + [_row(row) for row in message["inline"]]
    if scene.get("menu"):
        lines += [MENU[lang], *(_row(row) for row in scene["menu"])]
    return "\n".join(lines)


def _cell(scene: str, transcript: dict[str, Any], lang: str) -> str:
    dark, light = (f"docs/images/{picture(scene, theme, lang)}" for theme in ("dark", "light"))
    text = html.escape(alt(transcript[scene], lang), quote=False).replace('"', "&quot;")
    return (
        f'    <td width="50%" valign="top"><picture>'
        f'<source media="(prefers-color-scheme: dark)" srcset="{dark}">'
        f'<img src="{light}" width="{WIDTH}" alt="{text}"></picture></td>'
    )


def render(transcript: dict[str, Any], lang: str) -> str:
    """The block between the markers, from a language's transcript."""
    rows = [
        "  <tr>\n" + "\n".join(_cell(scene, transcript, lang) for scene in pair) + "\n  </tr>"
        for pair in PAIRS
    ]
    return "\n<table>\n" + "\n".join(rows) + "\n</table>\n"


def _bounds(text: str) -> tuple[int, int]:
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        raise ValueError(f"the README has no markers {START} … {END}")
    return start + len(START), end


def between(text: str) -> str:
    """What a README holds between the markers."""
    start, end = _bounds(text)
    return text[start:end]


def replace(text: str, block: str) -> str:
    """The README with `block` between the markers and the rest as it was."""
    start, end = _bounds(text)
    return text[:start] + block + text[end:]


def write(path: Path, block: str) -> bool:
    """Puts the block into the README at `path`; whether that changed it."""
    text = path.read_text(encoding="utf-8")
    changed = replace(text, block)
    if changed != text:
        path.write_text(changed, encoding="utf-8", newline="\n")
    return changed != text
