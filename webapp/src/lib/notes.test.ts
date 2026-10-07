import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { codePoints } from "./format";
import { cleanItem, doneCount, MAX_ITEM } from "./notes";
import { getNotesQuery, setNotesQuery, useNotesQuery } from "./notesSearch";

describe("an item of a checklist", () => {
  it("is kept as the server keeps it: one line, single spaces, no space at the ends", () => {
    expect(cleanItem("  молоко\t2 л  ")).toBe("молоко 2 л");
    expect(cleanItem("хлеб\r\nбелый")).toBe("хлеб белый");
    // Every control character is a space, the C1 ones and DEL too; a no-break space is white space.
    expect(cleanItem("a\u0000b\u007fc\u0085d\u009fe\u00a0\u3000f")).toBe("a b c d e f");
    expect(cleanItem(" \t\n ")).toBe("");
    // Emoji and their joiners stay whole.
    expect(cleanItem(" 👩‍👩‍👧 ☑️ ")).toBe("👩‍👩‍👧 ☑️");
  });

  it("is measured in characters: 100 emoji fit", () => {
    expect(codePoints(cleanItem("😀".repeat(MAX_ITEM)))).toBe(100);
  });

  it("counts a checklist's checked items", () => {
    expect(doneCount([{ done: true }, { done: false }, { done: true }])).toBe(2);
    expect(doneCount([])).toBe(0);
  });
});

describe("the search of the notes", () => {
  it("keeps its query until the app closes and tells every screen that shows it", () => {
    const { result, unmount } = renderHook(() => useNotesQuery());
    expect(result.current).toBe("");
    act(() => setNotesQuery("wifi"));
    expect(result.current).toBe("wifi");
    unmount();
    // A screen shown again (back from a note) finds it where it was.
    expect(renderHook(() => useNotesQuery()).result.current).toBe("wifi");
    expect(getNotesQuery()).toBe("wifi");
  });
});
