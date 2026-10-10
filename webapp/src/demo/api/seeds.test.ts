import { describe, expect, it } from "vitest";
import { addDaysIso } from "../../lib/format";
import { seed } from "./seeds";
import { DAY } from "./time";

// Wednesday 7 October 2026, 10:30 in Moscow.
const MORNING = Date.UTC(2026, 9, 7, 7, 30);

describe("the demo's data", () => {
  it("are the same for the same moment: one ?at=, one picture", () => {
    expect(seed("ru", MORNING)).toEqual(seed("ru", MORNING));
    expect(seed("en", MORNING)).toEqual(seed("en", MORNING));
  });

  it("keep a past day as it was and give each new day its own", () => {
    const today = seed("ru", MORNING);
    const later = seed("ru", MORNING + 3 * DAY);
    const before = (day: string) => day < "2026-10-07";
    for (const habit of today.habits) {
      // A habit began so many days ago: three days later, it began three days later too.
      const after = later.habits.find((other) => other.name === habit.name);
      const kept = [...habit.marks].filter(([day]) => before(day) && day >= (after?.created_on ?? ""));
      expect(kept.length).toBeGreaterThan(0);
      expect(kept.every(([day, done]) => after?.marks.get(day) === done), habit.name).toBe(true);
    }
    const spent = (data: typeof today) =>
      data.entries.filter((entry) => before(entry.day)).map(({ amount, note, day }) => [day, note, amount]);
    expect(spent(later).filter(([day]) => String(day) >= "2026-08-01")).toEqual(spent(today));
    expect(later.entries.some((entry) => entry.day > addDaysIso("2026-10-07", 1))).toBe(true);
  });

  it("are the visitor's, in the language the demo was opened in", () => {
    const ru = seed("ru", MORNING);
    expect(ru.profile).toEqual({
      first_name: "Саша", language: "auto",
      home: { name: "Москва", lat: 55.75222, lon: 37.61556, timezone: "Europe/Moscow" },
      morning: { enabled: true, time: "08:00" }, can_write: true, currency: "RUB", budget: 3_000_000,
    });
    expect(ru.cities.map((city) => city.name)).toEqual(["Тула", "Петропавловск-Камчатский", "Ереван"]);
    expect(ru.group.name).toBe("ДЕМО-01-26");
    const en = seed("en", MORNING);
    expect(en.profile.first_name).toBe("Alex");
    expect(en.profile.home.name).toBe("Moscow");
    expect(en.cities.map((city) => city.name)).toEqual(["Tula", "Petropavlovsk-Kamchatsky", "Yerevan"]);
    expect(en.notes.map((note) => note.text)).toContain("Door code: 45B7");
    expect(en.habits.map((habit) => habit.name)).toEqual(["Sport", "Read 20 pages", "Swimming", "No sugar"]);
    expect(en.timetable.every((lesson) => lesson.kind === null)).toBe(true);
  });

  it("give every record its own id and the next one after them", () => {
    const data = seed("ru", MORNING);
    const ids = (list: { id: number }[]) => list.map((item) => item.id);
    for (const [kind, list] of [
      ["note", data.notes], ["city", data.cities], ["reminder", data.reminders], ["habit", data.habits],
      ["entry", data.entries], ["category", data.categories],
    ] as const) {
      expect(new Set(ids(list)).size, kind).toBe(list.length);
      expect(data.next[kind], kind).toBeGreaterThan(Math.max(0, ...ids(list)));
    }
    const items = data.notes.flatMap((note) => note.items);
    expect(new Set(ids(items)).size).toBe(items.length);
    expect(data.next.item).toBeGreaterThan(Math.max(0, ...ids(items)));
  });

  it("have money from the first days of the month before last up to today, and habits open today", () => {
    const data = seed("ru", MORNING);
    const days = data.entries.map((entry) => entry.day).sort();
    expect(days[0]?.slice(0, 7)).toBe("2026-08");
    expect(days.filter((day) => day > "2026-10-07")).toEqual([]);
    expect(days.filter((day) => day >= "2026-10-01").length).toBeGreaterThan(5);
    expect(data.habits.every((habit) => !habit.marks.has("2026-10-07"))).toBe(true);
    expect(data.categories).toHaveLength(16);
    expect(data.categories.filter((category) => category.budget !== null).map((category) => category.preset))
      .toEqual(["cafe", "fun"]);
  });
});
