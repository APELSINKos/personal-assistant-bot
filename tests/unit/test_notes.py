from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from aiogram.types import Chat, Message, MessageEntity
from sqlalchemy import func, select

from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import NoteItem
from assistant.core.services import notes
from assistant.core.services.notes import Item

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
ROOT = Path(__file__).resolve().parents[2]
# The search cases the app's lib/search.ts is tested with as well: the bot and the app must find
# the same notes.
SEARCH_CASES: list[dict[str, Any]] = json.loads(
    (ROOT / "webapp" / "src" / "lib" / "searchCases.json").read_text(encoding="utf-8")
)
ITEM_LENGTH = {"field": "items", "reason": "length", "limit": 100}
QUERY_LENGTH = {"field": "query", "reason": "length", "limit": 50}


async def texts_of(session, user_id: int = 1) -> list[str]:
    return [view.text for view in await notes.list_for(session, user_id)]


async def stored_items(session) -> int:
    return int(await session.scalar(select(func.count()).select_from(NoteItem)))


async def test_a_note_keeps_the_moment_it_was_made(session, make_user) -> None:
    await make_user()
    view = await notes.create(session, 1, "  купить хлеб  ", now=NOW)
    assert (view.text, view.pinned_at, view.created_at, view.updated_at) == (
        "купить хлеб",
        None,
        NOW,
        NOW,
    )
    assert view.items == [] and not view.pinned and (view.done, view.total) == (0, 0)
    assert await notes.get_view(session, 1, view.id) == view


async def test_the_newest_note_comes_first(session, make_user) -> None:
    await make_user()
    for text in ("первая", "вторая", "третья"):
        await notes.create(session, 1, text, now=NOW)
    assert await texts_of(session) == ["третья", "вторая", "первая"]


async def test_pinned_notes_come_first_the_last_pinned_on_top(session, make_user) -> None:
    await make_user()
    a, b, c, d, e = [await notes.create(session, 1, text, now=NOW) for text in "abcde"]
    await notes.set_pinned(session, 1, a.id, True, NOW)
    await notes.set_pinned(session, 1, c.id, True, LATER)
    assert await texts_of(session) == ["c", "a", "e", "d", "b"]
    await notes.set_pinned(session, 1, d.id, True, NOW)  # pinned at the same moment as «a»
    assert await texts_of(session) == ["c", "d", "a", "e", "b"]


@pytest.mark.parametrize(("length", "ok"), [(1, True), (499, True), (500, True), (501, False)])
async def test_length_boundaries(session, make_user, length: int, ok: bool) -> None:
    await make_user()
    if ok:
        assert len((await notes.create(session, 1, "x" * length, now=NOW)).text) == length
    else:
        with pytest.raises(InvalidInput) as error:
            await notes.create(session, 1, "x" * length, now=NOW)
        assert error.value.params == {"field": "text", "reason": "length", "limit": 500}


@pytest.mark.parametrize("text", ["", "   ", "\n"])
async def test_empty_rejected(session, make_user, text: str) -> None:
    await make_user()
    with pytest.raises(InvalidInput):
        await notes.create(session, 1, text, now=NOW)


async def test_lengths_are_counted_in_characters(session, make_user) -> None:
    # An emoji is one character, as the app counts too, though Telegram counts it as two.
    await make_user()
    view = await notes.create(session, 1, "🎉" * 500, ["🎉" * 100], now=NOW)
    assert (len(view.text), len(view.items[0].text)) == (500, 100)
    with pytest.raises(InvalidInput):
        await notes.create(session, 1, "🎉" * 501, now=NOW)
    with pytest.raises(InvalidInput):
        await notes.create(session, 1, "Покупки", ["🎉" * 101], now=NOW)


async def test_limit_of_50(session, make_user) -> None:
    await make_user()
    for i in range(50):
        await notes.create(session, 1, f"n{i}", now=NOW)
    with pytest.raises(LimitReached) as error:
        await notes.create(session, 1, "one more", now=NOW)
    assert error.value.params == {"entity": "note", "limit": 50}


async def test_a_checklist_is_made_in_one_go(session, make_user) -> None:
    await make_user()
    view = await notes.create(
        session, 1, "Покупки", [" молоко ", "хлеб\tбородинский"], pinned=True, now=NOW
    )
    assert view.pinned_at == NOW and view.pinned
    assert [(item.text, item.done) for item in view.items] == [
        ("молоко", False),
        ("хлеб бородинский", False),
    ]
    assert view.items[0].id < view.items[1].id
    assert await notes.get_view(session, 1, view.id) == view


async def test_a_checklist_has_up_to_twenty_items(session, make_user) -> None:
    await make_user()
    full = await notes.create(session, 1, "Покупки", [f"п{i}" for i in range(20)], now=NOW)
    assert full.total == 20
    with pytest.raises(LimitReached) as error:
        await notes.create(session, 1, "Ещё", [f"п{i}" for i in range(21)], now=NOW)
    assert error.value.params == {"entity": "note_item", "limit": 20}
    assert await notes.count(session, 1) == 1 and await stored_items(session) == 20


@pytest.mark.parametrize("item", ["", "  ", "\t\n", "я" * 101])
async def test_a_bad_item_writes_nothing(session, make_user, item: str) -> None:
    await make_user()
    with pytest.raises(InvalidInput) as error:
        await notes.create(session, 1, "Покупки", ["молоко", item], now=NOW)
    assert error.value.params == ITEM_LENGTH
    assert await notes.count(session, 1) == 0 and await stored_items(session) == 0


async def test_another_users_note_is_out_of_reach(session, make_user) -> None:
    await make_user(id=1)
    await make_user(id=2)
    note = await notes.create(session, 1, "secret", ["пункт"], now=NOW)
    item = note.items[0]
    for call in (
        lambda: notes.get_view(session, 2, note.id),
        lambda: notes.update_text(session, 2, note.id, "hacked"),
        lambda: notes.set_pinned(session, 2, note.id, True, NOW),
        lambda: notes.add_items(session, 2, note.id, ["чужое"]),
        lambda: notes.set_item(session, 2, note.id, item.id, True),
        lambda: notes.delete_item(session, 2, note.id, item.id),
        lambda: notes.clear_done(session, 2, note.id),
    ):
        with pytest.raises(NotFound) as error:
            await call()
        assert error.value.params == {"entity": "note"}
    assert await notes.list_for(session, 2) == [] and await notes.pinned(session, 2) == []
    assert await notes.search(session, 2, "secret") == []
    assert await notes.delete(session, 2, note.id) is False
    assert await notes.get_view(session, 1, note.id) == note
    assert await notes.delete(session, 1, note.id) is True
    assert await notes.delete(session, 1, note.id) is False
    assert await stored_items(session) == 0  # the items went with their note


async def test_a_pin_is_not_an_edit(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Пароль от wifi", now=NOW)
    pinned = await notes.set_pinned(session, 1, note.id, True, LATER)
    assert (pinned.pinned_at, pinned.updated_at) == (LATER, NOW)
    # Pinning a pinned note keeps the first pin: an old card and the app may both ask.
    assert await notes.set_pinned(session, 1, note.id, True, LATER + timedelta(hours=1)) == pinned
    unpinned = await notes.set_pinned(session, 1, note.id, False, LATER)
    assert (unpinned.pinned_at, unpinned.updated_at) == (None, NOW)
    assert await notes.set_pinned(session, 1, note.id, False, LATER) == unpinned
    with pytest.raises(NotFound):
        await notes.set_pinned(session, 1, note.id + 1, True, NOW)


async def test_at_most_five_pinned_notes(session, make_user) -> None:
    await make_user()
    views = [await notes.create(session, 1, f"n{i}", now=NOW) for i in range(6)]
    for view in views[:5]:
        await notes.set_pinned(session, 1, view.id, True, NOW)
    with pytest.raises(LimitReached) as error:
        await notes.set_pinned(session, 1, views[5].id, True, NOW)
    assert error.value.params == {"entity": "pinned_note", "limit": 5}
    # A pinned note pinned again is not counted twice.
    assert (await notes.set_pinned(session, 1, views[0].id, True, LATER)).pinned_at == NOW
    with pytest.raises(LimitReached) as error:
        await notes.create(session, 1, "ещё одна", pinned=True, now=NOW)
    assert error.value.params == {"entity": "pinned_note", "limit": 5}
    assert await notes.count(session, 1) == 6  # the refused note was not made
    await notes.set_pinned(session, 1, views[0].id, False, NOW)
    assert (await notes.set_pinned(session, 1, views[5].id, True, NOW)).pinned


async def test_a_new_text_keeps_the_items_and_the_pin(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Покупки", ["молоко"], pinned=True, now=NOW)
    edited = await notes.update_text(session, 1, note.id, "  Покупки на неделю ")
    assert edited.text == "Покупки на неделю"
    assert (edited.items, edited.pinned_at, edited.created_at) == (note.items, NOW, NOW)
    assert edited.updated_at != NOW  # the text is the one edit that moves it
    assert await notes.update_text(session, 1, note.id, "Покупки на неделю") == edited
    with pytest.raises(InvalidInput):
        await notes.update_text(session, 1, note.id, "x" * 501)
    with pytest.raises(NotFound):
        await notes.update_text(session, 1, note.id + 1, "x")


async def test_items_are_added_at_the_end_all_or_none(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Покупки", ["молоко"], now=NOW)
    added = await notes.add_items(session, 1, note.id, ["хлеб", " сыр\n"])
    assert [(item.text, item.done) for item in added] == [("хлеб", False), ("сыр", False)]
    view = await notes.get_view(session, 1, note.id)
    assert view.items == [*note.items, *added] and view.updated_at == NOW
    with pytest.raises(InvalidInput) as error:
        await notes.add_items(session, 1, note.id, ["яйца", "я" * 101])
    assert error.value.params == ITEM_LENGTH
    assert (await notes.get_view(session, 1, note.id)).total == 3
    assert await notes.add_items(session, 1, note.id, []) == []


async def test_a_note_holds_up_to_twenty_items(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Покупки", [f"п{i}" for i in range(18)], now=NOW)
    with pytest.raises(LimitReached) as error:
        await notes.add_items(session, 1, note.id, ["a", "b", "c"])
    assert error.value.params == {"entity": "note_item", "limit": 20}
    assert (await notes.get_view(session, 1, note.id)).total == 18
    await notes.add_items(session, 1, note.id, ["a", "b"])
    with pytest.raises(LimitReached):
        await notes.add_items(session, 1, note.id, ["c"])
    assert (await notes.get_view(session, 1, note.id)).total == 20


async def test_an_item_is_set_not_switched(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Покупки", ["молоко", "хлеб"], now=NOW)
    milk = note.items[0]
    assert await notes.set_item(session, 1, note.id, milk.id, True) == Item(milk.id, "молоко", True)
    # «✅ молоко» of an old card pressed once more: the item stays checked.
    assert (await notes.set_item(session, 1, note.id, milk.id, True)).done
    view = await notes.get_view(session, 1, note.id)
    assert [item.done for item in view.items] == [True, False]
    assert (view.done, view.total, view.updated_at) == (1, 2, NOW)
    assert not (await notes.set_item(session, 1, note.id, milk.id, False)).done


async def test_an_item_is_reached_only_through_its_note(session, make_user) -> None:
    await make_user()
    shopping = await notes.create(session, 1, "Покупки", ["молоко"], now=NOW)
    trip = await notes.create(session, 1, "Поездка", ["паспорт"], now=NOW)
    passport = trip.items[0]
    for call in (
        lambda: notes.set_item(session, 1, shopping.id, passport.id, True),
        lambda: notes.delete_item(session, 1, shopping.id, passport.id),
    ):
        with pytest.raises(NotFound) as error:
            await call()
        assert error.value.params == {"entity": "note_item"}
    await notes.delete(session, 1, trip.id)
    with pytest.raises(NotFound) as error:
        await notes.set_item(session, 1, trip.id, passport.id, True)
    assert error.value.params == {"entity": "note"}


async def test_items_go_one_by_one_or_all_checked_at_once(session, make_user) -> None:
    await make_user()
    note = await notes.create(session, 1, "Покупки", ["молоко", "хлеб", "сыр", "яйца"], now=NOW)
    milk, bread, cheese, eggs = note.items
    await notes.delete_item(session, 1, note.id, bread.id)
    with pytest.raises(NotFound) as error:
        await notes.delete_item(session, 1, note.id, bread.id)
    assert error.value.params == {"entity": "note_item"}
    assert await notes.clear_done(session, 1, note.id) == 0
    await notes.set_item(session, 1, note.id, milk.id, True)
    await notes.set_item(session, 1, note.id, eggs.id, True)
    assert await notes.clear_done(session, 1, note.id) == 2
    view = await notes.get_view(session, 1, note.id)
    assert view.items == [cheese] and view.updated_at == NOW


async def test_the_first_pinned_notes_with_their_items(session, make_user) -> None:
    await make_user()
    assert await notes.pinned(session, 1) == []
    views = [await notes.create(session, 1, f"n{i}", [f"п{i}"], now=NOW) for i in range(5)]
    # Pinned in an order that is neither the notes' order nor its reverse: the last pinned first.
    for minutes, number in enumerate([1, 3, 0, 2]):
        await notes.set_pinned(session, 1, views[number].id, True, NOW + timedelta(minutes=minutes))
    shown = await notes.pinned(session, 1)
    assert [view.text for view in shown] == ["n2", "n0", "n3"]
    assert [item.text for item in shown[0].items] == ["п2"]
    every = await notes.pinned(session, 1, limit=5)
    assert [view.text for view in every] == ["n2", "n0", "n3", "n1"]  # «n4» is not pinned


def test_the_search_cases_are_well_formed() -> None:
    # A misspelt key would pass unseen on the app's side.
    assert all(set(case) == {"text", "items", "query", "match"} for case in SEARCH_CASES)
    assert {case["match"] for case in SEARCH_CASES} == {True, False}


@pytest.mark.parametrize("case", SEARCH_CASES, ids=lambda case: str(case["query"]))
async def test_the_search_finds_what_the_app_finds(session, make_user, case) -> None:
    await make_user()
    note = await notes.create(session, 1, case["text"], case["items"], now=NOW)
    found = await notes.search(session, 1, case["query"])
    assert [view.id for view in found] == ([note.id] if case["match"] else [])


async def test_the_search_keeps_the_order_of_the_list(session, make_user) -> None:
    await make_user()
    home = await notes.create(session, 1, "WiFi дома: hunter2", now=NOW)
    await notes.create(session, 1, "Купить молоко", now=NOW)
    dacha = await notes.create(session, 1, "Дача", ["пароль от wifi"], now=NOW)
    guests = await notes.create(session, 1, "Для гостей: wifi guest", now=NOW)
    await notes.set_pinned(session, 1, dacha.id, True, NOW)
    # The pinned one, then the newest: neither the order the notes were made in nor its reverse.
    found = await notes.search(session, 1, "wifi")
    assert [view.id for view in found] == [dacha.id, guests.id, home.id]
    assert await notes.search(session, 1, "я" * 50) == []


@pytest.mark.parametrize("query", ["", "   ", "я" * 51])
async def test_a_search_is_one_to_fifty_characters(session, make_user, query: str) -> None:
    await make_user()
    with pytest.raises(InvalidInput) as error:
        await notes.search(session, 1, query)
    assert error.value.params == QUERY_LENGTH


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("Пароль от WiFi", "пароль от wifi"),
        ("ЁЛКА", "елка"),
        ("  Ёжик\n\tв   тумане ", "ежик в тумане"),
        ("Straße", "straße"),  # lower case, not casefold: the app's JavaScript has no casefold
        ("ΣΑΣ", "σας"),
    ],
)
def test_fold(text: str, folded: str) -> None:
    assert notes.fold(text) == folded


@pytest.mark.parametrize(
    ("text", "cleaned"),
    [
        ("  молоко ", "молоко"),
        ("хлеб\tбородинский\n", "хлеб бородинский"),
        ("сыр  \x00 российский", "сыр российский"),
        ("\r\n", ""),
    ],
)
def test_clean_item(text: str, cleaned: str) -> None:
    assert notes.clean_item(text) == cleaned


def test_item_lines_lose_their_markers() -> None:
    lines = [
        "- молоко",
        "– хлеб",
        "— сыр",
        "• яйца",
        "* соль",
        "· сахар",
        "☐ мука",
        "☑ масло",
        "✅ чай",
        "✔ кофе",
        "⬜ рис",
        "[ ] вода",
        "[x] сок",
        "[X] морс",
        "[\N{CYRILLIC SMALL LETTER HA}] квас",
        "[\N{CYRILLIC CAPITAL LETTER HA}] кефир",
        "[] мёд",
        "1. яблоки",
        "2) груши",
        "100. сливы",
        "   - лук  ",
    ]
    assert notes.parse_item_lines("\n".join(lines)) == [
        "молоко",
        "хлеб",
        "сыр",
        "яйца",
        "соль",
        "сахар",
        "мука",
        "масло",
        "чай",
        "кофе",
        "рис",
        "вода",
        "сок",
        "морс",
        "квас",
        "кефир",
        "мёд",
        "яблоки",
        "груши",
        "сливы",
        "лук",
    ]


def test_a_mark_goes_with_the_selector_an_emoji_keyboard_adds() -> None:
    # «☑️», «✔️» and «⬜️» from an emoji keyboard: the mark, then the invisible U+FE0F.
    message = "\n".join(
        [
            "\N{BALLOT BOX WITH CHECK}\N{VARIATION SELECTOR-16} молоко",
            "\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16} хлеб",
            "\N{WHITE LARGE SQUARE}\N{VARIATION SELECTOR-16} сыр",
        ]
    )
    assert notes.parse_item_lines(message) == ["молоко", "хлеб", "сыр"]


def test_markers_in_a_row_all_go() -> None:
    message = "\n".join(["- [ ] молоко", "1. [x] хлеб", "* ☐ сыр", "- - - - чай"])
    # At most three markers in a row: a fourth dash is the item's own.
    assert notes.parse_item_lines(message) == ["молоко", "хлеб", "сыр", "- чай"]


@pytest.mark.parametrize(
    "line",
    [
        "1.5 кг муки",  # a marker only before a space or the end of the line
        "1)молоко",
        "-5 градусов",
        "–хлеб",
        "[x]сок",
        "1000. молоко",
        "молоко - 2 л",
    ],
)
def test_item_lines_without_a_marker_stay(line: str) -> None:
    assert notes.parse_item_lines(line) == [line]


def test_item_lines_skip_the_empty_ones() -> None:
    message = "\n".join(
        [
            "молоко\r",
            "",
            "   ",
            "- ",
            "\N{BALLOT BOX WITH CHECK}\N{VARIATION SELECTOR-16}",
            "хлеб\tбородинский",
        ]
    )
    assert notes.parse_item_lines(message) == ["молоко", "хлеб бородинский"]
    assert notes.parse_item_lines("") == []


def link(offset: int, length: int, url: str) -> MessageEntity:
    return MessageEntity(type="text_link", offset=offset, length=length, url=url)


def test_a_hidden_link_is_written_out_after_its_words() -> None:
    # Telegram counts in UTF-16: «🔥» is two units, so «тут» starts at 10.
    entities = [link(10, 3, "https://example.com/sale")]
    assert (
        notes.expand_links("🔥 Скидки тут", entities) == "🔥 Скидки тут (https://example.com/sale)"
    )


def test_a_caption_has_its_links_written_out_too() -> None:
    photo = Message(
        message_id=1,
        date=NOW,
        chat=Chat(id=1, type="private"),
        caption="Чек тут",
        caption_entities=[link(4, 3, "https://example.com/receipt")],
    )
    expanded = notes.expand_links(photo.caption or "", photo.caption_entities)
    assert expanded == "Чек тут (https://example.com/receipt)"


def test_hidden_links_are_written_out_from_the_last() -> None:
    entities = [link(9, 3, "https://b.example/2"), link(3, 3, "https://a.example/1")]
    expanded = "🎉 раз (https://a.example/1) и два (https://b.example/2)"
    assert notes.expand_links("🎉 раз и два", entities) == expanded
    assert notes.expand_links("🎉 раз и два", entities[::-1]) == expanded


def test_only_hidden_links_change_the_text() -> None:
    text = "Жирный example.com"
    entities = [
        MessageEntity(type="bold", offset=0, length=6),
        MessageEntity(type="url", offset=7, length=11),
    ]
    assert notes.expand_links(text, entities) == text
    assert notes.expand_links(text, None) == text


@pytest.mark.parametrize(
    "words", ["https://example.com/sale", "example.com/sale", "http://example.com/sale/"]
)
def test_a_link_showing_its_own_address_stays(words: str) -> None:
    text = f"Тут {words}"
    assert notes.expand_links(text, [link(4, len(words), "https://example.com/sale")]) == text
