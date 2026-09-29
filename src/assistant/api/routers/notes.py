"""Notes: list, create, edit, delete."""

from __future__ import annotations

from fastapi import APIRouter, Response

from assistant.api.deps import CurrentUser, ItemId, Session
from assistant.api.schemas import NoteIn, NoteOut
from assistant.api.views import note_out
from assistant.core.errors import NotFound
from assistant.core.services import notes

router = APIRouter(tags=["notes"])


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(user: CurrentUser, db: Session) -> list[NoteOut]:
    return [note_out(note) for note in await notes.all_for(db, user.id)]


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(body: NoteIn, user: CurrentUser, db: Session) -> NoteOut:
    note = await notes.create(db, user.id, body.text)
    await db.commit()
    return note_out(note)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(note_id: ItemId, body: NoteIn, user: CurrentUser, db: Session) -> NoteOut:
    note = await notes.update(db, user.id, note_id, body.text)
    await db.commit()
    return note_out(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: ItemId, user: CurrentUser, db: Session) -> Response:
    if not await notes.delete(db, user.id, note_id):
        raise NotFound(entity="note")
    await db.commit()
    return Response(status_code=204)
