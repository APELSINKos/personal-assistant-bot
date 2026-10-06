import { describe, expect, it } from "vitest";
import { shownChance } from "../lib/format";
import { NBSP } from "../lib/money";
import { en } from "./en";
import { hasErrorText, resolveLang } from "./index";
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

  it("keeps a Russian percent of the weather on one line with its number", () => {
    expect(ru.weather.humidity(71)).toBe(`Влажность 71${NBSP}%`);
    expect(en.weather.humidity(71)).toBe("Humidity 71%");
    expect(ru.weather.chance(shownChance(40))).toBe(`💧 40${NBSP}%`);
    expect(en.weather.chance(shownChance(40))).toBe("💧 40%");
    // A line of «Сегодня» that wraps keeps the drop with its number too.
    expect(ru.today.withChance(ru.today.tomorrow("☁️", "+2…+7°"), shownChance(80))).toBe(
      `Завтра: ☁️ +2…+7°, 💧${NBSP}80${NBSP}%`,
    );
    expect(en.today.withChance(en.today.tomorrow("☁️", "+2…+7°"), shownChance(80))).toBe(
      `Tomorrow: ☁️ +2…+7°, 💧${NBSP}80%`,
    );
  });

  it("leaves a chance of precipitation under 20 % unsaid", () => {
    expect(ru.weather.chance(shownChance(19))).toBe("");
    expect(en.weather.chance(shownChance(null))).toBe("");
    expect(ru.today.withChance(ru.today.tomorrow("☁️", "+2…+7°"), shownChance(10))).toBe("Завтра: ☁️ +2…+7°");
    expect(en.today.withChance(en.today.tomorrow("☁️", "+2…+7°"), shownChance(null))).toBe("Tomorrow: ☁️ +2…+7°");
    // @ts-expect-error A forecast's own chance does not fit without shownChance: 0 would read «осадки 0 %».
    ru.weather.hourLabel("15:00", "пасмурно", "+7°", 0);
  });

  it("names the gusts of the wind only when there are some", () => {
    expect(ru.weather.wind("3", "6")).toBe("Ветер 3 м/с, порывы до 6 м/с");
    expect(ru.weather.wind("3", null)).toBe("Ветер 3 м/с");
    expect(en.weather.wind("3", "6")).toBe("Wind 3 m/s, gusts up to 6 m/s");
    expect(en.weather.wind("3", null)).toBe("Wind 3 m/s");
  });

  it("reads out an hour and a day, with a chance only from 20 %", () => {
    expect(ru.weather.hourLabel("15:00", "пасмурно", "+7°", shownChance(40))).toBe(
      `15:00, пасмурно, +7°, осадки 40${NBSP}%`,
    );
    expect(ru.weather.hourLabel("15:00", "пасмурно", "+7°", shownChance(0))).toBe("15:00, пасмурно, +7°");
    expect(ru.weather.dayLabel("Среда, 7 октября", "ясно", "+3°", "+9°", shownChance(20))).toBe(
      `Среда, 7 октября: ясно, от +3° до +9°, осадки 20${NBSP}%`,
    );
    expect(en.weather.dayLabel("Wednesday, October 7", "clear", "+3°", "+9°", shownChance(null))).toBe(
      "Wednesday, October 7: clear, +3° to +9°",
    );
    expect(en.weather.hourLabel("15:00", "overcast", "+7°", shownChance(40))).toBe(
      "15:00, overcast, +7°, precipitation 40%",
    );
  });

  it("words the weather of the way to classes and back", () => {
    expect(ru.today.classes("09:00", "+3°", "16:20", ru.today.withChance("+6°", shownChance(70, 30)))).toBe(
      `🎓 На пары (09:00): +3° · после пар (16:20): +6°, 💧${NBSP}70${NBSP}%`,
    );
    expect(ru.today.classesAfter("16:20", "+6°")).toBe("🎓 После пар (16:20): +6°");
    expect(en.today.classes("09:00", "+3°", "16:20", "+6°")).toBe("🎓 To classes (09:00): +3° · after (16:20): +6°");
  });

  it("knows which error codes have texts of their own", () => {
    expect(["limit_pinned_note", "limit_note_item", "limit_city", "duplicate_city"].every(hasErrorText)).toBe(true);
    expect(hasErrorText("limit_note")).toBe(false); // 50 notes: the app says so before asking
    expect(hasErrorText("constructor")).toBe(false);
  });
});
