"""Notes: list, create, edit, pin, delete, and the items of a checklist."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from assistant.api.deps import CurrentUser, ItemId, Session, State
from assistant.api.schemas import NoteIn, NoteItemIn, NoteItemOut, NoteItemPatch, NoteOut, NotePatch
from assistant.api.views import item_out, note_out
from assistant.core.errors import InvalidInput, NotFound
from assistant.core.services import notes

router = APIRouter(tags=["notes"])


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(user: CurrentUser, db: Session) -> list[NoteOut]:
    return [note_out(note) for note in await notes.list_for(db, user.id)]


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(body: NoteIn, user: CurrentUser, db: Session, state: State) -> NoteOut:
    note = await notes.create(
        db, user.id, body.text, body.items, pinned=body.pinned, now=state.clock()
    )
    await db.commit()
    return note_out(note)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: ItemId, body: NotePatch, user: CurrentUser, db: Session, state: State
) -> NoteOut:
    """A new text, a pin, or both. Nothing is kept until both are done: a refused pin leaves
    the old text too."""
    if body.text is None and body.pinned is None:
        raise InvalidInput(field="note", reason="empty")
    if body.text is not None:
        await notes.update_text(db, user.id, note_id, body.text)
    if body.pinned is not None:
        await notes.set_pinned(db, user.id, note_id, body.pinned, state.clock())
    note = await notes.get_view(db, user.id, note_id)
    await db.commit()
    return note_out(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await notes.delete(db, user.id, note_id):
        raise NotFound(entity="note")
    await db.commit()
    return Response(status_code=204)


@router.post("/notes/{note_id}/items", response_model=NoteItemOut, status_code=201)
async def add_item(
    note_id: ItemId, body: NoteItemIn, user: CurrentUser, db: Session
) -> NoteItemOut:
    [item] = await notes.add_items(db, user.id, note_id, [body.text])
    await db.commit()
    return item_out(item)


@router.patch("/notes/{note_id}/items/{item_id}", response_model=NoteItemOut)
async def set_item(
    note_id: ItemId, item_id: ItemId, body: NoteItemPatch, user: CurrentUser, db: Session
) -> NoteItemOut:
    item = await notes.set_item(db, user.id, note_id, item_id, body.done)
    await db.commit()
    return item_out(item)


@router.delete("/notes/{note_id}/items/{item_id}", status_code=204)
async def delete_item(note_id: ItemId, item_id: ItemId, user: CurrentUser, db: Session) -> Response:
    await notes.delete_item(db, user.id, note_id, item_id)
    await db.commit()
    return Response(status_code=204)


@router.delete("/notes/{note_id}/items", status_code=204)
async def clear_done(
    note_id: ItemId,
    done: Annotated[Literal["true"], Query()],
    user: CurrentUser,
    db: Session,
) -> Response:
    """Remove the checked items, if any. `done=true` must be there: a request without it would
    read as one that empties the whole list."""
    await notes.clear_done(db, user.id, note_id)
    await db.commit()
    return Response(status_code=204)
