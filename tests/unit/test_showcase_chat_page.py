from __future__ import annotations

import re
from typing import Any

import pytest
from scripts.showcase import chat_page, readme

# A scene as chats.py records it: the user writes, the bot answers with buttons, and the next
# morning the bot writes again.
SCENE: dict[str, Any] = {
    "messages": [
        {"from": "user", "at": "2026-10-07T12:40", "text": "кофе <250>", "inline": []},
        {
            "from": "bot",
            "at": "2026-10-07T12:40",
            "text": "✅ ☕ Кафе — 250\u00a0₽ · кофе\n\n    🟩🟩⬜  «серия»",
            "inline": [["🗂 Категория", "↩\ufe0f Отменить"], ["✓ Готово"]],
        },
        {"from": "bot", "at": "2026-10-08T07:30", "text": "Погода — open-meteo.com", "inline": []},
    ]
}
MENU = [["🌤 Погода", "📅 Мой день"], ["🎯 Привычки", "💰 Финансы"]]


def test_a_page_draws_the_chat_without_a_script_or_an_address() -> None:
    page = chat_page.html(SCENE, "ru", "dark")
    assert '<html lang="ru" class="dark">' in page
    assert "<script" not in page
    assert "http" not in page  # its fonts come from the run's own server, by path
    assert f'url("/showcase/fonts/{chat_page.TEXT_FILE}")' in page
    assert 'url("/showcase/fonts/Noto-COLRv1.ttf")' in page
    assert "кофе &lt;250&gt;" in page  # the text is escaped
    assert "white-space: pre-wrap" in page  # the habits' strips keep their leading spaces
    assert "    🟩🟩⬜  «серия»" in page
    assert '<span class="link">open-meteo.com</span>' in page


def test_the_user_s_bubble_alone_has_the_two_ticks() -> None:
    page = chat_page.html(SCENE, "en", "light")
    messages = page.split('<div class="message ')[1:]
    assert [message.split('"')[0] for message in messages] == ["out", "in", "in"]
    assert ['class="ticks"' in message for message in messages] == [True, False, False]
    assert '<span class="meta">12:40<svg class="ticks"' in messages[0]
    assert '<span class="meta">07:30</span>' in messages[2]


def test_the_last_bubble_of_a_run_has_the_tail() -> None:
    # A run is one sender's messages of one day: a date pill ends it too.
    def tails(scene: dict[str, Any]) -> list[bool]:
        page = chat_page.html(scene, "ru", "dark")
        return ['class="tail"' in message for message in page.split('<div class="message ')[1:]]

    assert tails(SCENE) == [True, True, True]
    same_day = {**SCENE["messages"][2], "at": "2026-10-07T12:40"}
    assert tails({"messages": [*SCENE["messages"][:2], same_day]}) == [True, False, True]


def test_a_date_pill_marks_a_new_day_only() -> None:
    page = chat_page.html(SCENE, "ru", "dark")
    assert page.count('class="pill"') == 1
    assert page.index("Отменить") < page.index(">8 октября<") < page.index("open-meteo")
    assert ">October 8<" in chat_page.html(SCENE, "en", "dark")


def test_the_buttons_keep_their_rows_and_the_menu_comes_last() -> None:
    page = chat_page.html(SCENE, "ru", "light")
    rows = re.findall(r'<div class="row">(.*?)</div>', page)
    assert [re.findall(r'<span class="button">(.*?)</span>', row) for row in rows] == [
        ["🗂 Категория", "↩\ufe0f Отменить"],
        ["✓ Готово"],
    ]
    assert 'class="menu"' not in page
    with_menu = chat_page.html({**SCENE, "menu": MENU}, "ru", "light")
    keys = re.findall(r'<span class="key">(.*?)</span>', with_menu)
    assert keys == ["🌤 Погода", "📅 Мой день", "🎯 Привычки", "💰 Финансы"]
    assert with_menu.index('class="menu"') > with_menu.index("open-meteo")


def test_every_text_the_page_draws_is_checked_against_the_fonts() -> None:
    drawn = chat_page.texts({**SCENE, "menu": MENU}, "ru")
    for text in ("кофе <250>", "✓ Готово", "8 октября", "12:40", "07:30", "💰 Финансы"):
        assert text in drawn


def test_an_alt_text_is_the_chat_written_out() -> None:
    assert readme.alt({**SCENE, "menu": MENU}, "ru") == "\n".join(
        [
            "Ты: кофе <250>",
            "Бот: ✅ ☕ Кафе — 250 ₽ · кофе",
            "    🟩🟩⬜  «серия»",
            "[🗂 Категория] [↩\ufe0f Отменить]",
            "[✓ Готово]",
            "8 октября",
            "Бот: Погода — open-meteo.com",
            "Меню:",
            "[🌤 Погода] [📅 Мой день]",
            "[🎯 Привычки] [💰 Финансы]",
        ]
    )
    # The bot alone: its messages as they are, as the README's text blocks showed the digest.
    morning = {"messages": SCENE["messages"][1:2]}
    assert readme.alt(morning, "en").startswith("✅ ☕ Кафе — 250 ₽ · кофе\n    🟩")


def test_the_block_shows_six_pictures_in_two_columns() -> None:
    scenes = {
        name: {"messages": [{**SCENE["messages"][2], "text": f'"{name}"'}]} for name in readme.ORDER
    }
    block = readme.render(scenes, "en")
    assert block.startswith("\n<table>\n") and block.endswith("</table>\n")
    assert block.count("<tr>") == 3 and block.count("<picture>") == 6
    pictures = re.findall(r'srcset="docs/images/chat/(\w+)\.dark\.en\.webp"', block)
    assert pictures == ["morning", "week", "reminder", "money", "habits", "checklist"]
    week = '<img src="docs/images/chat/week.light.en.webp" width="390" alt="&quot;week&quot;">'
    assert week in block  # the alt text is the chat's, its quotes escaped
    assert "\n\n" not in block.strip()  # a blank line would end the README's HTML block
    assert readme.picture("week", "dark", "ru") == "chat/week.dark.webp"


def test_the_block_is_written_between_its_markers_only() -> None:
    text = f"# Title\n\n{readme.START}\nold\n{readme.END}\n\n## Mini App\n"
    assert readme.between(text) == "\nold\n"
    assert (
        readme.replace(text, "\nnew\n")
        == f"# Title\n\n{readme.START}\nnew\n{readme.END}\n\n## Mini App\n"
    )
    with pytest.raises(ValueError, match="markers"):
        readme.replace("# Title\n", "\nnew\n")
