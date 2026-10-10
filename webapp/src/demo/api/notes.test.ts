import { describe, expect, it } from "vitest";
import type { Note, NoteItem } from "../../api/types";
import { demoApi, MORNING, problem } from "./testApi";
import { HOUR } from "./time";

const NO_CONTENT = { status: 204, body: null, headers: {} };

describe("the notes (routers/notes.py, services/notes.py)", () => {
  it("GET /notes: the pinned on top, the last pinned first, then the newest", () => {
    const notes = demoApi().read<Note[]>("GET /notes");
    expect(notes.map((note) => [note.id, note.pinned])).toEqual([
      [1, true], [2, true], [3, true], [8, false], [7, false], [6, false], [5, false], [4, false],
    ]);
    expect(notes[0]).toEqual({
      id: 1, text: "Покупки", pinned: true,
      items: [
        { id: 1, text: "молоко", done: true }, { id: 2, text: "хлеб", done: true }, { id: 3, text: "яйца", done: true },
        { id: 4, text: "сыр", done: false }, { id: 5, text: "яблоки", done: false }, { id: 6, text: "кофе", done: false },
        { id: 7, text: "макароны", done: false },
      ],
      created_at: new Date(MORNING - 336 * HOUR).toISOString().replace(".000", ""),
      updated_at: new Date(MORNING - 336 * HOUR).toISOString().replace(".000", ""),
    });
    expect(notes[1]?.items.map((item) => [item.id, item.done])).toEqual([
      [8, true], [9, true], [10, true], [11, true], [12, false], [13, false], [14, false], [15, false],
    ]);
  });

  it("POST /notes: a note, a checklist with its items, pinned at once if asked", () => {
    const { read, call } = demoApi();
    const created = call("POST /notes", { text: "  Купить  ", items: [" носки\t ", "шарф"], pinned: true });
    expect(created.status).toBe(201);
    expect(created.body).toMatchObject({
      id: 9, text: "Купить", pinned: true,
      items: [{ id: 16, text: "носки", done: false }, { id: 17, text: "шарф", done: false }],
    });
    expect(read<Note[]>("GET /notes")[0]?.id).toBe(9);
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
    expect(call("POST /notes", { text: "📌 4", pinned: true }).status).toBe(201);
    expect(call("POST /notes", { text: "📌 5", pinned: true }).status).toBe(201);
    expect(call("POST /notes", { text: "📌 6", pinned: true })).toEqual(
      problem(409, "limit_reached", { entity: "pinned_note", limit: 5 }),
    );
    for (let count = 11; count <= 50; count += 1) expect(call("POST /notes", { text: `${count}` }).status).toBe(201);
    expect(call("POST /notes", { text: "51" })).toEqual(problem(409, "limit_reached", { entity: "note", limit: 50 }));
  });

  it("PATCH /notes/{note_id}: a new text, a pin, or both — all or nothing", () => {
    const { read, call, setNow } = demoApi();
    setNow(MORNING + HOUR);
    const edited = read<Note>("PATCH /notes/7", { text: "Курсовая: план готов" });
    expect(edited).toMatchObject({ id: 7, text: "Курсовая: план готов", pinned: false, updated_at: "2026-10-07T08:30:00Z" });
    expect(read<Note>("PATCH /notes/7", { pinned: true })).toMatchObject({ pinned: true, updated_at: "2026-10-07T08:30:00Z" });
    expect(read<Note[]>("GET /notes")[0]?.id).toBe(7);
    call("POST /notes", { text: "a", pinned: true });
    expect(call("PATCH /notes/6", { text: "Блины на завтрак", pinned: true })).toEqual(
      problem(409, "limit_reached", { entity: "pinned_note", limit: 5 }),
    );
    expect(read<Note[]>("GET /notes").find((note) => note.id === 6)?.text).toMatch(/^Блины: /);
    expect(call("PATCH /notes/7", {})).toEqual(problem(422, "validation_error", { field: "note", reason: "empty" }));
    expect(call("PATCH /notes/99", { pinned: false })).toEqual(problem(404, "not_found", { entity: "note" }));
  });

  it("DELETE /notes/{note_id}: gone with its items, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/2")).toEqual(NO_CONTENT);
    expect(read<Note[]>("GET /notes").map((note) => note.id)).toEqual([1, 3, 8, 7, 6, 5, 4]);
    expect(call("DELETE /notes/2")).toEqual(problem(404, "not_found", { entity: "note" }));
  });
});

describe("the items of a checklist (routers/notes.py)", () => {
  /** The items of «Собрать в поездку», the second checklist. */
  const packing = (notes: Note[]) => notes.find((note) => note.id === 2)?.items ?? [];

  it("POST /notes/{note_id}/items: one more at the end, up to 20", () => {
    const { call } = demoApi();
    const added = call("POST /notes/2/items", { text: " носки " });
    expect(added).toMatchObject({ status: 201, body: { id: 16, text: "носки", done: false } });
    for (let count = 10; count <= 20; count += 1) expect(call("POST /notes/2/items", { text: `${count}` }).status).toBe(201);
    expect(call("POST /notes/2/items", { text: "21" })).toEqual(problem(409, "limit_reached", { entity: "note_item", limit: 20 }));
    expect(call("POST /notes/3/items", { text: "" })).toEqual(
      problem(422, "validation_error", { field: "items", reason: "length", limit: 100 }),
    );
    expect(call("POST /notes/99/items", { text: "a" })).toEqual(problem(404, "not_found", { entity: "note" }));
  });

  it("PATCH /notes/{note_id}/items/{item_id}: checked or not, as asked", () => {
    const { read, call } = demoApi();
    expect(read<NoteItem>("PATCH /notes/2/items/12", { done: true })).toEqual({ id: 12, text: "свитер", done: true });
    expect(read<NoteItem>("PATCH /notes/2/items/12", { done: true })).toEqual({ id: 12, text: "свитер", done: true });
    expect(read<NoteItem>("PATCH /notes/2/items/8", { done: false }).done).toBe(false);
    expect(call("PATCH /notes/2/items/99", { done: true })).toEqual(problem(404, "not_found", { entity: "note_item" }));
    expect(call("PATCH /notes/3/items/12", { done: true })).toEqual(problem(404, "not_found", { entity: "note_item" }));
    expect(call("PATCH /notes/99/items/12", { done: true })).toEqual(problem(404, "not_found", { entity: "note" }));
    expect(call("PATCH /notes/2/items/12", {})).toEqual(problem(422, "validation_error", { field: "done" }));
  });

  it("DELETE /notes/{note_id}/items/{item_id}: one item, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/2/items/9")).toEqual(NO_CONTENT);
    expect(packing(read<Note[]>("GET /notes")).map((item) => item.id)).toEqual([8, 10, 11, 12, 13, 14, 15]);
    expect(call("DELETE /notes/2/items/9")).toEqual(problem(404, "not_found", { entity: "note_item" }));
  });

  it("DELETE /notes/{note_id}/items?done=true: the checked ones go, the open ones keep their places", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /notes/2/items?done=true")).toEqual(NO_CONTENT);
    expect(packing(read<Note[]>("GET /notes")).map((item) => item.text)).toEqual(["свитер", "зубная щётка", "книга", "билеты"]);
    expect(call("DELETE /notes/2/items")).toEqual(problem(422, "validation_error", { field: "done", detail: "Field required" }));
    expect(call("DELETE /notes/2/items?done=false")).toEqual(problem(422, "validation_error", { field: "done" }));
    expect(call("DELETE /notes/99/items?done=true")).toEqual(problem(404, "not_found", { entity: "note" }));
  });
});
