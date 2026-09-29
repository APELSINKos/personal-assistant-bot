"""Notes: short texts owned by a user."""

from __future__ import annotations

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core.config import LIMITS
from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.models import Note


def _clean(text: str) -> str:
    cleaned = text.strip()
    if not 1 <= len(cleaned) <= LIMITS.note_length:
        raise InvalidInput(field="text", reason="length", limit=LIMITS.note_length)
    return cleaned


async def all_for(session: AsyncSession, user_id: int) -> list[Note]:
    result = await session.scalars(select(Note).where(Note.user_id == user_id).order_by(Note.id))
    return list(result.all())


async def count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Note).where(Note.user_id == user_id))
        or 0
    )


async def get(session: AsyncSession, user_id: int, note_id: int) -> Note:
    note = await session.scalar(select(Note).where(Note.id == note_id, Note.user_id == user_id))
    if note is None:
        raise NotFound(entity="note")
    return note


async def create(session: AsyncSession, user_id: int, text: str) -> Note:
    cleaned = _clean(text)
    if await count(session, user_id) >= LIMITS.notes:
        raise LimitReached(entity="note", limit=LIMITS.notes)
    note = Note(user_id=user_id, text=cleaned)
    session.add(note)
    await session.flush()
    return note


async def update(session: AsyncSession, user_id: int, note_id: int, text: str) -> Note:
    note = await get(session, user_id, note_id)
    note.text = _clean(text)
    await session.flush()
    return note


async def delete(session: AsyncSession, user_id: int, note_id: int) -> bool:
    result = await session.execute(
        sql_delete(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
