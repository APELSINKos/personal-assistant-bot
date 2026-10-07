"""Notes: short texts owned by a user. A note can be pinned on top of the list, and a note with
items is a checklist whose text is the list's title.

The bot and the app change one note from two processes, so a note is always read anew from its
rows as a NoteView, never from an object a session keeps: a pin and an item are written by
statements that such an object would not see. The items are separate rows, so a check made in the
bot and one made in the app never overwrite each other; the text goes to whoever saves it last.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Note, NoteItem

# A list marker at the start of an item's line: a dash, a bullet, a ballot box or a check mark
# (with the U+FE0F an emoji keyboard adds), «[ ]» or «[x]» (a Latin or a Cyrillic «x»), or a
# number with a dot or a bracket — each only before a space or the end of the line, so that
# «1.5 кг» and «-5 градусов» stay whole.
_MARKER = re.compile(
    r"^\s*(?:[-–—•*·☐☑✅✔⬜]\N{VARIATION SELECTOR-16}?|\[[ xXхХ]?\]|\d{1,3}[.)])(?=\s|$)\s*"
)
# Markers can come in a row: «- [ ] молоко», «1. ☐ хлеб».
_MARKERS_IN_A_ROW = 3
_SCHEME = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class Item:
    id: int
    text: str
    done: bool


@dataclass(frozen=True)
class NoteView:
    id: int
    text: str  # a checklist's title
    pinned_at: datetime | None  # None: not pinned
    created_at: datetime
    updated_at: datetime  # the last change of the text: pins and items leave it as it is
    items: list[Item] = field(default_factory=list)  # in the order they were added

    @property
    def pinned(self) -> bool:
        return self.pinned_at is not None

    @property
    def done(self) -> int:
        """The checked items: a checklist shows «✅ done/total»."""
        return sum(1 for item in self.items if item.done)

    @property
    def total(self) -> int:
        return len(self.items)


class LinkEntity(Protocol):
    """What expand_links reads of a message entity; aiogram's MessageEntity has it."""

    @property
    def type(self) -> str: ...

    @property
    def offset(self) -> int: ...  # in UTF-16 code units, as Telegram counts

    @property
    def length(self) -> int: ...

    @property
    def url(self) -> str | None: ...


def _clean(text: str) -> str:
    cleaned = text.strip()
    if not 1 <= len(cleaned) <= LIMITS.note_length:
        raise InvalidInput(field="text", reason="length", limit=LIMITS.note_length)
    return cleaned


def clean_item(text: str) -> str:
    """An item as kept, one line: control characters (a tab, a line break) become spaces, runs of
    spaces one space, and the ends go."""
    spaced = "".join(" " if unicodedata.category(char) == "Cc" else char for char in text)
    return " ".join(spaced.split())


def _clean_items(texts: Iterable[str]) -> list[str]:
    cleaned = [clean_item(text) for text in texts]
    if any(not 1 <= len(text) <= LIMITS.note_item_length for text in cleaned):
        raise InvalidInput(field="items", reason="length", limit=LIMITS.note_item_length)
    return cleaned


def parse_item_lines(text: str) -> list[str]:
    """The items of a message, one per line, without the list markers a line starts with;
    empty lines are skipped. A ticked box («☑», «[x]») goes like any marker: a new item is
    open."""
    items = []
    for line in text.splitlines():
        for _ in range(_MARKERS_IN_A_ROW):
            bare = _MARKER.sub("", line, count=1)
            if bare == line:
                break
            line = bare
        item = clean_item(line)
        if item:
            items.append(item)
    return items


def fold(text: str) -> str:
    """A text as the search compares it, the same way as lib/search.ts in the app: lower case,
    «ё» as «е», runs of white space as one space. Not casefold: JavaScript has none, and its
    toLowerCase keeps «ß» and «ς» where casefold would not."""
    return " ".join(text.lower().replace("ё", "е").split())


def expand_links(text: str, entities: Iterable[LinkEntity] | None) -> str:
    """A message's text with each hidden link written out after its words, «тут (https://…)»:
    a note keeps only text. A link whose words are its own address stays as it is, and other
    formatting does not change the text. Telegram counts offsets in UTF-16 code units."""
    links: list[tuple[int, int, str]] = []
    for entity in entities or ():
        if entity.type == "text_link" and entity.url:
            links.append((entity.offset, entity.length, entity.url))
    units = text.encode("utf-16-le")
    # From the last link to the first: what is written after a link moves only the ones after it.
    for offset, length, url in sorted(links, reverse=True):
        end = (offset + length) * 2
        words = units[offset * 2 : end].decode("utf-16-le")
        if _bare(words) != _bare(url):
            units = units[:end] + f" ({url})".encode("utf-16-le") + units[end:]
    return units.decode("utf-16-le")


def _bare(address: str) -> str:
    return _SCHEME.sub("", address).removesuffix("/")


async def _views(
    session: AsyncSession, *where: ColumnElement[bool], limit: int | None = None
) -> list[NoteView]:
    """The notes `where` holds, with their items, in the order of every list: the pinned ones on
    top, the last pinned first, then the newest first."""
    rows = (
        await session.execute(
            select(Note.id, Note.text, Note.pinned_at, Note.created_at, Note.updated_at)
            .where(*where)
            .order_by(Note.pinned_at.is_(None), Note.pinned_at.desc(), Note.id.desc())
            .limit(limit)
        )
    ).all()
    items: dict[int, list[Item]] = {row.id: [] for row in rows}
    if items:
        found = await session.execute(
            select(NoteItem.note_id, NoteItem.id, NoteItem.text, NoteItem.done)
            .where(NoteItem.note_id.in_(list(items)))
            .order_by(NoteItem.id)
        )
        for note_id, item_id, text, done in found:
            items[note_id].append(Item(item_id, text, done))
    return [
        NoteView(row.id, row.text, row.pinned_at, row.created_at, row.updated_at, items[row.id])
        for row in rows
    ]


async def list_for(session: AsyncSession, user_id: int) -> list[NoteView]:
    return await _views(session, Note.user_id == user_id)


async def get_view(session: AsyncSession, user_id: int, note_id: int) -> NoteView:
    found = await _views(session, Note.id == note_id, Note.user_id == user_id)
    if not found:
        raise NotFound(entity="note")
    return found[0]


async def pinned(session: AsyncSession, user_id: int, limit: int = 3) -> list[NoteView]:
    """The first pinned notes of the list: «Мой день» and «Сегодня» show three."""
    return await _views(session, Note.user_id == user_id, Note.pinned_at.is_not(None), limit=limit)


async def search(session: AsyncSession, user_id: int, query: str) -> list[NoteView]:
    """The notes whose text or items hold every word of `query`, each anywhere, part of a word
    too, in the order of the list. InvalidInput(field="query") for a query that is empty or
    longer than LIMITS.search_length."""
    cleaned = query.strip()
    if not 1 <= len(cleaned) <= LIMITS.search_length:
        raise InvalidInput(field="query", reason="length", limit=LIMITS.search_length)
    words = fold(cleaned).split()
    return [view for view in await list_for(session, user_id) if _holds(view, words)]


def _holds(view: NoteView, words: list[str]) -> bool:
    # What is searched is what is kept, the «(address)» of a written-out link included. A word
    # is found within the text or within one item, never across them.
    haystack = "\n".join([fold(view.text), *(fold(item.text) for item in view.items)])
    return all(word in haystack for word in words)


async def count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Note).where(Note.user_id == user_id))
        or 0
    )


async def _pinned_count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Note)
            .where(Note.user_id == user_id, Note.pinned_at.is_not(None))
        )
        or 0
    )


async def create(
    session: AsyncSession,
    user_id: int,
    text: str,
    items: Sequence[str] = (),
    *,
    pinned: bool = False,
    now: datetime,
) -> NoteView:
    """A new note with its items, pinned if asked, written whole or, when anything is wrong, not
    at all. `now` is the caller's clock: the note's moment (and its pin's) is the one the caller
    compares with."""
    cleaned = _clean(text)
    lines = _clean_items(items)
    if len(lines) > LIMITS.note_items:
        raise LimitReached(entity="note_item", limit=LIMITS.note_items)
    # Checked before writing and without a lock: the bot and the app at once may end one note
    # over a limit, which nothing minds.
    if await count(session, user_id) >= LIMITS.notes:
        raise LimitReached(entity="note", limit=LIMITS.notes)
    if pinned and await _pinned_count(session, user_id) >= LIMITS.pinned_notes:
        raise LimitReached(entity="pinned_note", limit=LIMITS.pinned_notes)
    note = Note(
        user_id=user_id,
        text=cleaned,
        created_at=now,
        updated_at=now,
        pinned_at=now if pinned else None,
    )
    session.add(note)
    await session.flush()
    rows = [NoteItem(note_id=note.id, text=line, done=False, created_at=now) for line in lines]
    session.add_all(rows)
    await session.flush()
    return NoteView(
        note.id, cleaned, note.pinned_at, now, now, [Item(row.id, row.text, False) for row in rows]
    )


async def update_text(session: AsyncSession, user_id: int, note_id: int, text: str) -> NoteView:
    """A new text for the note; its items and pin stay. The text is the one change that moves
    updated_at, and the same text again changes nothing."""
    view = await get_view(session, user_id, note_id)
    cleaned = _clean(text)
    if cleaned == view.text:
        return view
    await session.execute(
        update(Note).where(Note.id == note_id, Note.user_id == user_id).values(text=cleaned)
    )
    return await get_view(session, user_id, note_id)


async def set_pinned(
    session: AsyncSession, user_id: int, note_id: int, pinned: bool, now: datetime
) -> NoteView:
    """Pin the note on top of the list at `now`, the last pinned first, or take the pin off.
    Pinning a pinned note, or unpinning one that is not, changes nothing: an old card in the chat
    and the app may both ask. A pin is not an edit: updated_at is written as it is, since the
    column's onupdate would move it."""
    view = await get_view(session, user_id, note_id)
    if view.pinned == pinned:
        return view
    if pinned and await _pinned_count(session, user_id) >= LIMITS.pinned_notes:
        raise LimitReached(entity="pinned_note", limit=LIMITS.pinned_notes)
    await session.execute(
        update(Note)
        .where(Note.id == note_id, Note.user_id == user_id)
        .values(pinned_at=now if pinned else None, updated_at=Note.updated_at)
    )
    return await get_view(session, user_id, note_id)


async def _require(session: AsyncSession, user_id: int, note_id: int) -> None:
    """NotFound unless the note is the user's: an item is reached only through its note."""
    found = await session.scalar(select(Note.id).where(Note.id == note_id, Note.user_id == user_id))
    if found is None:
        raise NotFound(entity="note")


async def add_items(
    session: AsyncSession, user_id: int, note_id: int, texts: Sequence[str]
) -> list[Item]:
    """New open items at the end of the note's list: all of them, or none when one is wrong or
    they would take the note past LIMITS.note_items. The note's updated_at stays."""
    await _require(session, user_id, note_id)
    lines = _clean_items(texts)
    held = await session.scalar(
        select(func.count()).select_from(NoteItem).where(NoteItem.note_id == note_id)
    )
    if (held or 0) + len(lines) > LIMITS.note_items:
        raise LimitReached(entity="note_item", limit=LIMITS.note_items)
    rows = [NoteItem(note_id=note_id, text=line, done=False) for line in lines]
    session.add_all(rows)
    await session.flush()
    return [Item(row.id, row.text, False) for row in rows]


async def set_item(
    session: AsyncSession, user_id: int, note_id: int, item_id: int, done: bool
) -> Item:
    """Check or uncheck an item. The state is set, not switched: an old card's button does what
    it shows and never undoes a check made in the app. NotFound with entity "note" when the note
    is gone, "note_item" when only the item is."""
    await _require(session, user_id, note_id)
    row = (
        await session.execute(
            update(NoteItem)
            .where(NoteItem.id == item_id, NoteItem.note_id == note_id)
            .values(done=done)
            .returning(NoteItem.text)
        )
    ).one_or_none()
    if row is None:
        raise NotFound(entity="note_item")
    return Item(item_id, row.text, done)


async def delete_item(session: AsyncSession, user_id: int, note_id: int, item_id: int) -> None:
    await _require(session, user_id, note_id)
    result = await session.execute(
        sql_delete(NoteItem).where(NoteItem.id == item_id, NoteItem.note_id == note_id)
    )
    if not result.rowcount:  # type: ignore[attr-defined]
        raise NotFound(entity="note_item")


async def clear_done(session: AsyncSession, user_id: int, note_id: int) -> int:
    """Remove the checked items; how many went. The open ones keep their places."""
    await _require(session, user_id, note_id)
    result = await session.execute(
        sql_delete(NoteItem).where(NoteItem.note_id == note_id, NoteItem.done.is_(True))
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def delete(session: AsyncSession, user_id: int, note_id: int) -> bool:
    """Whether the note was there to delete; its items go with it."""
    result = await session.execute(
        sql_delete(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
