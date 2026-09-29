import { describe, expect, it } from "vitest";
import {
  addDaysIso, bigDate, formatNumber, formatTemp, groupByDay, localTimeHm, localTodayIso,
  shortDay, timeOf,
} from "./format";

describe("format", () => {
  it("builds the big date", () => {
    expect(bigDate("2026-09-28", "ru")).toEqual({
      day: "28", weekday: "понедельник", month: "сентябрь", year: "2026",
    });
    expect(bigDate("2026-09-28", "en")).toEqual({
      day: "28", weekday: "Monday", month: "September", year: "2026",
    });
  });

  it("formats numbers and temperatures", () => {
    expect(formatNumber(84.1975, "ru")).toBe("84,20");
    expect(formatNumber(1500.5, "ru")).toBe("1 500,50");
    expect(formatNumber(1500.5, "en")).toBe("1,500.50");
    expect([9.6, -3.7, -0.4, 0.2, null].map(formatTemp)).toEqual(["+10°", "-4°", "0°", "0°", "—"]);
  });

  it("does date arithmetic in the city's zone", () => {
    expect(addDaysIso("2026-12-31", 1)).toBe("2027-01-01");
    const late = new Date("2026-09-28T22:30:00Z");
    expect(localTodayIso("Europe/Moscow", late)).toBe("2026-09-29");
    expect(localTodayIso("UTC", late)).toBe("2026-09-28");
    expect(localTimeHm("Europe/Moscow", late)).toBe("01:30");
  });

  it("groups reminders by day", () => {
    const items = [
      { id: 1, due_local: "2026-09-29T09:00" },
      { id: 2, due_local: "2026-09-28T19:30" },
      { id: 3, due_local: "2026-10-02T08:00" },
      { id: 4, due_local: "2026-09-28T08:15" },
    ];
    const groups = groupByDay(items, "2026-09-28", "ru", { today: "Сегодня", tomorrow: "Завтра" });
    expect(groups.map((g) => g.label)).toEqual(["Сегодня", "Завтра", "Пт, 2 окт."]);
    expect(groups[0]?.items.map((i) => i.id)).toEqual([4, 2]);
    expect(shortDay("2026-10-02", "en")).toBe("Fri, Oct 2");
    expect(timeOf("2026-09-28T19:30")).toBe("19:30");
  });
});
