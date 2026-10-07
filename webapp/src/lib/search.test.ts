import { describe, expect, it } from "vitest";
import { fold, matches, searchNotes } from "./search";
import cases from "./searchCases.json";

interface SearchCase {
  text: string;
  items: string[];
  query: string;
  match: boolean;
}

// The bot reads the same table in tests/unit/test_notes.py: both sides must find the same notes.
const CASES: SearchCase[] = cases;

const note = (text: string, ...items: string[]) => ({ text, items: items.map((item) => ({ text: item })) });

describe("the search of notes", () => {
  it.each(CASES)("finds what the bot finds: «$query» in «$text» is $match", ({ text, items, query, match }) => {
    expect(matches(note(text, ...items), query)).toBe(match);
  });

  it("has cases of both kinds", () => {
    expect(CASES.every((item) => Object.keys(item).sort().join() === "items,match,query,text")).toBe(true);
    expect(new Set(CASES.map((item) => item.match))).toEqual(new Set([true, false]));
  });

  it("folds case, «ё» and white space as the bot does", () => {
    expect(fold("Пароль от WiFi")).toBe("пароль от wifi");
    expect(fold("ЁЛКА")).toBe("елка");
    expect(fold("  Ёжик\n\tв   тумане ")).toBe("ежик в тумане");
    // Lower case, not case folding: «ß» and the final «ς» stay.
    expect(fold("STRAßE ΣΑΣ")).toBe("straße σας");
  });

  it("takes white space exactly as Python's split() does", () => {
    const [nel, separator, nbsp, bom] = [0x85, 0x1c, 0xa0, 0xfeff].map((code) => String.fromCharCode(code));
    expect(fold(`a${nel}b${separator}c${nbsp}d`)).toBe("a b c d");
    expect(fold(`a${bom}b`)).toBe(`a${bom}b`); // no white space for Python
  });

  it("finds a word within the text or one item, never across them", () => {
    expect(matches(note("Покупки мол", "око"), "молоко")).toBe(false);
    expect(matches(note("Покупки", "молоко", "хлеб"), "хлеб молоко покупки")).toBe(true);
  });

  it("keeps the order of the list and gives all notes for an empty query", () => {
    const notes = [note("WiFi дома"), note("Купить молоко"), note("Дача", "пароль от wifi")];
    expect(searchNotes(notes, "wifi")).toEqual([notes[0], notes[2]]);
    expect(searchNotes(notes, "   ")).toEqual(notes);
    expect(searchNotes(notes, "")).toEqual(notes);
    expect(matches(note("что угодно"), "")).toBe(true);
  });
});
