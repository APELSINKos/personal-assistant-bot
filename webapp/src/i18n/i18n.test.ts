import { describe, expect, it } from "vitest";
import { en } from "./en";
import { resolveLang } from "./index";
import { ru } from "./ru";

function keys(value: unknown, prefix = ""): string[] {
  if (value === null || typeof value !== "object") return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, inner]) =>
    keys(inner, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n", () => {
  it("has the same keys in both languages", () => {
    expect(keys(en).sort()).toEqual(keys(ru).sort());
  });

  it.each([
    ["ru", "ru"], ["uk", "ru"], ["be", "ru"], ["kk", "ru"], ["en-US", "en"], ["de", "en"],
    [undefined, "en"], [null, "en"],
  ] as const)("resolves %s to %s", (code, lang) => {
    expect(resolveLang(code)).toBe(lang);
  });

  it("promises no cause or time a refusal cannot know", () => {
    // A calendar is refused for its size, time, memory, series or labels alike; a directory cut
    // short by an outage is retried a day later.
    expect(ru.errors.too_large).toBe("Календарь слишком большой или сложный — разобрать его не получится");
    expect(en.errors.too_large).toBe("The calendar is too big or too complex to read");
    expect(en.schedule.building).toBe(
      "The group directory isn't ready yet — if your group isn't there, try again later or connect the timetable by link.",
    );
  });

  it("pluralises Russian days and notes", () => {
    expect([1, 2, 5, 11, 21].map((n) => ru.habits.streakIn(n, "days"))).toEqual([
      "1 день", "2 дня", "5 дней", "11 дней", "21 день",
    ]);
    expect(ru.today.notes(3)).toBe("3 заметки");
    expect(en.today.notes(1)).toBe("1 note");
    expect(ru.habits.progress(12, 17)).toBe("12 из 17 дней");
    expect(ru.habits.progress(1, 1)).toBe("1 из 1 дня");
  });
});
