import { describe, expect, it } from "vitest";
import type { Note, NoteItem } from "../../api/types";
import { demoApi, MORNING, problem } from "./testApi";
import { HOUR } from "./time";

const NO_CONTENT = { status: 204, body: null, headers: {} };

describe("the notes (routers/notes.py, services/notes.py)", () => {
  it("GET /notes: the pinned on top, the last pinned first, then the newest", () => {
    const notes = demoApi().read<Note[]>("GET /notes");
    expect(notes.map((note) => [note.id, note.pinned])).toEqual([[4, true], [3, true], [2, false], [1, false]]);
    expect(notes[0]).toEqual({
      id: 4, text: "Собрать в поездку", pinned: true,
      items: [
        { id: 1, text: "паспорт", done: true }, { id: 2, text: "зарядка", done: true },
        { id: 3, text: "наушники", done: true }, { id: 4, text: "зонт", done: true },
        { id: 5, text: "свитер", done: false }, { id: 6, text: "зубная щётка", done: false },
        { id: 7, text: "книга", done: false }, { id: 8, text: "билеты", done: false },
      ],
      created_at: new Date(MORNING - 30 * HOUR).toISOString().replace(".000", ""),
      updated_at: new Date(MORNING - 30 * HOUR).toISOString().replace(".000", ""),
    });
  });

  it("POST /notes: a note, a checklist with its items, pinned at once if asked", () => {
    const { read, call } = demoApi();
    const created = call("POST /notes", { text: "  Купить  ", items: [" носки\t ", "шарф"], pinned: true });
    expect(created.status).toBe(201);
    expect(created.body).toMatchObject({
      id: 5, text: "Купить", pinned: true,
      items: [{ id: 9, text: "носки", done: false }, { id: 10, text: "шарф", done: false }],
    });
    expect(read<Note[]>("GET /notes")[0]?.id).toBe(5);
    expect(call("POST /notes", { text: " " })).toEqual(
      problem(422, "validation_error", { field: "text", reason: "length", limit: 500 }),
    );
    expect(call("POST /notes", { text: "x".repeat(501) })).toEqual(problem(422, "validation_error", { field: "text", limit: 500 }));
    expect(call("POST /notes", { text: "x", items: ["a", "\t"] })).toEqual(
      problem(422, "validation_error", { field: "items", reason: "length", limit: 100 }),
    );
    expect(call("POST /notes", { text: "x", items: Array.from({ length: 21 }, (_, i) => `${i}`) })).toEqual(
      problem(409, "limit_reached", { entity: "note_item", limit: 20 }),
    );
    expect(call("POST /notes", { text: "x", color: "mint" })).toEqual(problem(422, "validation_error", { field: "color" }));
  });

  it("POST /notes: up to 50 notes, up to 5 pinned", () => {
    const { call } = demoApi();
    expect(call("POST /notes", { text: "📌 3", pinned: true }).status).toBe(201);
    expect(call("POST /notes", { text: "📌 4", pinned: true }).status).toBe(201);
    expect(call("POST /notes", { text: "📌 5", pinned: true }).status).toBe(201);
    expect(call("POST /notes", { text: "📌 6", pinned: true })).toEqual(
      problem(409, "limit_reached", { entity: "pinned_note", limit: 5 }),
    );
    for (let count = 8; count <= 50; count += 1) expect(call("POST /notes", { text: `${count}` }).status).toBe(201);
    expect(call("POST /notes", { text: "51" })).toEqual(problem(409, "limit_reached", { entity: "note", limit: 50 }));
  });

  it("PATCH /notes/{note_id}: a new text, a pin, or both — all or nothing", () => {
    const { read, call, setNow } = demoApi();
    setNow(MORNING + HOUR);
    const edited = read<Note>("PATCH /notes/2", { text: "Курсовая: план готов" });
    expect(edited).toMatchObject({ id: 2, text: "Курсовая: план готов", pinned: false, updated_at: "2026-10-07T08:30:00Z" });
    expect(read<Note>("PATCH /notes/2", { pinned: true })).toMatchObject({ pinned: true, updated_at: "2026-10-07T08:30:00Z" });
    expect(read<Note[]>("GET /notes")[0]?.id).toBe(2);
    call("POST /notes", { text: "a", pinned: true });
    call("POST /notes", { text: "b", pinned: true });
    expect(call("PATCH /notes/1", { text: "Блины на завтрак", pinned: true })).toEqual(
      problem(409, "limit_reached", { entity: "pinned_note", limit: 5 }),
    );
    expect(read<Note[]>("GET /notes").find((note) => note.id === 1)?.text).toMatch(/^Блины: /);
    expect(call("PATCH /notes/2", {})).toEqual(problem(422, "validation_error", { field: "note", reason: "empty" }));
    expect(call("PATCH /notes/99", { pinned: false })).toEqual(problem(404, "not_found", { entity: "note" }));
  });

  it("DELETE /notes/{note_id}: gone with its items, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/4")).toEqual(NO_CONTENT);
    expect(read<Note[]>("GET /notes").map((note) => note.id)).toEqual([3, 2, 1]);
    expect(call("DELETE /notes/4")).toEqual(problem(404, "not_found", { entity: "note" }));
  });
});

describe("the items of a checklist (routers/notes.py)", () => {
  it("POST /notes/{note_id}/items: one more at the end, up to 20", () => {
    const { call } = demoApi();
    const added = call("POST /notes/4/items", { text: " носки " });
    expect(added).toMatchObject({ status: 201, body: { id: 9, text: "носки", done: false } });
    for (let count = 10; count <= 20; count += 1) expect(call("POST /notes/4/items", { text: `${count}` }).status).toBe(201);
    expect(call("POST /notes/4/items", { text: "21" })).toEqual(problem(409, "limit_reached", { entity: "note_item", limit: 20 }));
    expect(call("POST /notes/3/items", { text: "" })).toEqual(
      problem(422, "validation_error", { field: "items", reason: "length", limit: 100 }),
    );
    expect(call("POST /notes/99/items", { text: "a" })).toEqual(problem(404, "not_found", { entity: "note" }));
  });

  it("PATCH /notes/{note_id}/items/{item_id}: checked or not, as asked", () => {
    const { read, call } = demoApi();
    expect(read<NoteItem>("PATCH /notes/4/items/5", { done: true })).toEqual({ id: 5, text: "свитер", done: true });
    expect(read<NoteItem>("PATCH /notes/4/items/5", { done: true })).toEqual({ id: 5, text: "свитер", done: true });
    expect(read<NoteItem>("PATCH /notes/4/items/1", { done: false }).done).toBe(false);
    expect(call("PATCH /notes/4/items/99", { done: true })).toEqual(problem(404, "not_found", { entity: "note_item" }));
    expect(call("PATCH /notes/3/items/5", { done: true })).toEqual(problem(404, "not_found", { entity: "note_item" }));
    expect(call("PATCH /notes/99/items/5", { done: true })).toEqual(problem(404, "not_found", { entity: "note" }));
    expect(call("PATCH /notes/4/items/5", {})).toEqual(problem(422, "validation_error", { field: "done" }));
  });

  it("DELETE /notes/{note_id}/items/{item_id}: one item, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/4/items/2")).toEqual(NO_CONTENT);
    expect(read<Note[]>("GET /notes")[0]?.items.map((item) => item.id)).toEqual([1, 3, 4, 5, 6, 7, 8]);
    expect(call("DELETE /notes/4/items/2")).toEqual(problem(404, "not_found", { entity: "note_item" }));
  });

  it("DELETE /notes/{note_id}/items?done=true: the checked ones go, the open ones keep their places", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/4/items?done=true")).toEqual(NO_CONTENT);
    expect(read<Note[]>("GET /notes")[0]?.items.map((item) => item.text)).toEqual(["свитер", "зубная щётка", "книга", "билеты"]);
    expect(call("DELETE /notes/4/items")).toEqual(problem(422, "validation_error", { field: "done", detail: "Field required" }));
    expect(call("DELETE /notes/4/items?done=false")).toEqual(problem(422, "validation_error", { field: "done" }));
    expect(call("DELETE /notes/99/items?done=true")).toEqual(problem(404, "not_found", { entity: "note" }));
  });
});
