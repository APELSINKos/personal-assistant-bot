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

  it("pluralises Russian days and notes", () => {
    expect([1, 2, 5, 11, 21].map((n) => ru.habits.streak(n))).toEqual([
      "1 день", "2 дня", "5 дней", "11 дней", "21 день",
    ]);
    expect(ru.today.notes(3)).toBe("3 заметки");
    expect(en.today.notes(1)).toBe("1 note");
    expect(ru.habits.progress(12, 17)).toBe("12 из 17 дней");
    expect(ru.habits.progress(1, 1)).toBe("1 из 1 дня");
  });
});
