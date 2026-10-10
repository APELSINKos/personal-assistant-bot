import { describe, expect, it } from "vitest";
import { BOT_CHAT_URL } from "../../lib/links";
import { REPO_URL } from "../../screens/More";
import { LINKS, WORDS, type HostWords } from "./words";

const NBSP = "\u00a0";

/** The texts the page shows: all but the tab's title, which never wraps. */
function shown(words: HostWords): string[] {
  return Object.entries(words)
    .filter(([key]) => key !== "title")
    .flatMap(([, value]) => (typeof value === "string" ? [value] : Object.values(value)));
}

describe("the host page's links", () => {
  it("lead where the app's own do", () => {
    expect(LINKS.bot).toBe(BOT_CHAT_URL);
    expect(LINKS.source).toBe(REPO_URL);
  });
});

describe("the host page's words", () => {
  it("keep each dash on the line before it, and the rain's emoji with the word after it", () => {
    // A line never starts with «—», as in the app's dictionaries: the space before a dash does not break.
    const words = [WORDS.ru, WORDS.en];
    expect(words.flatMap(shown).filter((text) => text.replaceAll(`${NBSP}—`, "").includes("—"))).toEqual([]);
    for (const { tagline } of words) expect(tagline).toContain(`\u{1F327}${NBSP}`);
  });
});
