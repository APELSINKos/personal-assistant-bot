/**
 * The notes (routers/notes.py, services/notes.py): short texts, pinned on top of the list if asked,
 * and checklists whose items are checked one by one. A change is made whole or not at all.
 */
import type { Note, NoteItem } from "../../api/types";
import { codePoints } from "../../lib/format";
import { cleanItem, MAX_ITEM, MAX_ITEMS, MAX_NOTES, MAX_TEXT } from "../../lib/notes";
import type { StoredNote, Visit } from "./data";
import { created, invalidInput, json, limitReached, noContent, notFound, route, type Route } from "./http";
import { utc } from "./time";
import { check, itemId, queryText, type Fields } from "./validate";

/** LIMITS.pinned_notes. */
const PINNED = 5;

const NOTE_IN: Fields = {
  text: { type: "str", required: true, max: 10_000 },
  items: { type: "list" },
  pinned: { type: "bool" },
};
const NOTE_PATCH: Fields = {
  text: { type: "str", nullable: true, max: 10_000 },
  pinned: { type: "bool", nullable: true },
};
const ITEM_IN: Fields = { text: { type: "str", required: true } };
const ITEM_PATCH: Fields = { done: { type: "bool", required: true } };

/** The order of every list: the pinned on top, the last pinned first, then the newest first. */
export function noteOrder(notes: readonly StoredNote[]): StoredNote[] {
  return [...notes].sort((a, b) =>
    Number(a.pinned === null) - Number(b.pinned === null) || (b.pinned ?? 0) - (a.pinned ?? 0) || b.id - a.id);
}

function noteOut(note: StoredNote): Note {
  return {
    id: note.id, text: note.text, pinned: note.pinned !== null, items: note.items.map((item) => ({ ...item })),
    created_at: utc(note.created), updated_at: utc(note.updated),
  };
}

/** notes._clean: a text of 1 to 500 characters once its ends are trimmed. */
function cleanText(text: string): string {
  const cleaned = text.trim();
  if (codePoints(cleaned) < 1 || codePoints(cleaned) > MAX_TEXT) {
    throw invalidInput({ field: "text", reason: "length", limit: MAX_TEXT });
  }
  return cleaned;
}

/** notes._clean_items: each item one line of 1 to 100 characters. */
function cleanItems(texts: readonly string[]): string[] {
  const cleaned = texts.map(cleanItem);
  if (cleaned.some((text) => codePoints(text) < 1 || codePoints(text) > MAX_ITEM)) {
    throw invalidInput({ field: "items", reason: "length", limit: MAX_ITEM });
  }
  return cleaned;
}

const pinnedCount = (visit: Visit) => visit.data.notes.filter((note) => note.pinned !== null).length;

/** The user's note of a path, or 404: an item is reached only through its note. */
function noteOf(visit: Visit, id: number): StoredNote {
  const note = visit.data.notes.find((item) => item.id === id);
  if (!note) throw notFound("note");
  return note;
}

function itemOf(note: StoredNote, id: number): NoteItem {
  const item = note.items.find((entry) => entry.id === id);
  if (!item) throw notFound("note_item");
  return item;
}

export const NOTES: Route[] = [
  route("GET", "/notes", (visit) => json<Note[]>(noteOrder(visit.data.notes).map(noteOut))),
  route("POST", "/notes", (visit, { body }) => {
    check(body, NOTE_IN);
    const input = body as { text: string; items?: string[]; pinned?: boolean };
    const text = cleanText(input.text);
    const lines = cleanItems(input.items ?? []);
    if (lines.length > MAX_ITEMS) throw limitReached("note_item", MAX_ITEMS);
    if (visit.data.notes.length >= MAX_NOTES) throw limitReached("note", MAX_NOTES);
    if (input.pinned && pinnedCount(visit) >= PINNED) throw limitReached("pinned_note", PINNED);
    const now = visit.now();
    const note: StoredNote = {
      id: visit.data.next.note++, text, created: now, updated: now, pinned: input.pinned ? now : null,
      items: lines.map((line) => ({ id: visit.data.next.item++, text: line, done: false })),
    };
    visit.data.notes.push(note);
    return created<Note>(noteOut(note));
  }),
  route("PATCH", "/notes/{note_id}", (visit, { params, body }) => {
    const id = itemId(params.note_id ?? "", "note_id");
    check(body, NOTE_PATCH);
    const patch = body as { text?: string | null; pinned?: boolean | null };
    if (patch.text == null && patch.pinned == null) throw invalidInput({ field: "note", reason: "empty" });
    const note = noteOf(visit, id);
    const text = patch.text == null ? note.text : cleanText(patch.text);
    const pin = patch.pinned != null && patch.pinned !== (note.pinned !== null);
    // A refused pin keeps the old text too: nothing changes until both are allowed.
    if (pin && patch.pinned && pinnedCount(visit) >= PINNED) throw limitReached("pinned_note", PINNED);
    const now = visit.now();
    if (text !== note.text) Object.assign(note, { text, updated: now });
    if (pin) note.pinned = patch.pinned ? now : null;
    return json<Note>(noteOut(note));
  }),
  route("DELETE", "/notes/{note_id}", (visit, { params }) => {
    const note = noteOf(visit, itemId(params.note_id ?? "", "note_id"));
    visit.data.notes = visit.data.notes.filter((item) => item !== note);
    return noContent();
  }),
  route("POST", "/notes/{note_id}/items", (visit, { params, body }) => {
    const id = itemId(params.note_id ?? "", "note_id");
    check(body, ITEM_IN);
    const note = noteOf(visit, id);
    const [line = ""] = cleanItems([(body as { text: string }).text]);
    if (note.items.length + 1 > MAX_ITEMS) throw limitReached("note_item", MAX_ITEMS);
    const item: NoteItem = { id: visit.data.next.item++, text: line, done: false };
    note.items.push(item);
    return created<NoteItem>({ ...item });
  }),
  route("PATCH", "/notes/{note_id}/items/{item_id}", (visit, { params, body }) => {
    const id = itemId(params.note_id ?? "", "note_id");
    const itemNumber = itemId(params.item_id ?? "", "item_id");
    check(body, ITEM_PATCH);
    const item = itemOf(noteOf(visit, id), itemNumber);
    item.done = (body as { done: boolean }).done;
    return json<NoteItem>({ ...item });
  }),
  route("DELETE", "/notes/{note_id}/items/{item_id}", (visit, { params }) => {
    const id = itemId(params.note_id ?? "", "note_id");
    const itemNumber = itemId(params.item_id ?? "", "item_id");
    const note = noteOf(visit, id);
    const item = itemOf(note, itemNumber);
    note.items = note.items.filter((entry) => entry !== item);
    return noContent();
  }),
  // «Убрать отмеченные»: done=true must be there, so that no request empties the whole list.
  route("DELETE", "/notes/{note_id}/items", (visit, { params, query }) => {
    const id = itemId(params.note_id ?? "", "note_id");
    const done = queryText(query, "done", { required: true });
    if (done !== "true") throw invalidInput({ detail: "Input should be 'true'", field: "done" });
    const note = noteOf(visit, id);
    note.items = note.items.filter((item) => !item.done);
    return noContent();
  }),
];
