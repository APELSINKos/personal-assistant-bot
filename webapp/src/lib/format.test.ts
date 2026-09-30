import { describe, expect, it } from "vitest";
import {
  addDaysIso, bigDate, dayHeading, daysBetween, formatNumber, formatTemp, localTimeHm,
  localTodayIso, monthGrid, monthTitle, rangeLabel, weekOf, weekdayShort,
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
    // The thousands separator below is a no-break space (U+00A0), as Intl writes it for ru.
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
});

describe("calendar helpers", () => {
  const labels = { today: "Сегодня", tomorrow: "Завтра", afterTomorrow: "Послезавтра", yesterday: "Вчера" };

  it("builds the week around a day, Monday first", () => {
    expect(weekOf("2026-09-30")).toEqual([
      "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    ]);
    expect(weekOf("2026-10-04")[0]).toBe("2026-09-28"); // Sunday belongs to the week before
  });

  it("builds a month grid of whole weeks", () => {
    const grid = monthGrid("2026-09-15");
    expect(grid[0]?.[0]).toBe("2026-08-31");
    expect(grid.at(-1)?.at(-1)).toBe("2026-10-04");
    expect(grid.every((week) => week.length === 7)).toBe(true);
  });

  it("names the day relative to today", () => {
    expect(dayHeading("2026-09-29", "2026-09-29", "ru", labels)).toBe("Сегодня · вторник, 29 сентября");
    expect(dayHeading("2026-10-01", "2026-09-29", "ru", labels)).toBe("Послезавтра · четверг, 1 октября");
    expect(dayHeading("2026-09-28", "2026-09-29", "ru", labels)).toBe("Вчера · понедельник, 28 сентября");
    expect(dayHeading("2026-10-06", "2026-09-29", "ru", labels)).toBe("Вторник, 6 октября");
    expect(daysBetween("2026-09-29", "2026-10-06")).toBe(7);
  });

  it("formats short labels", () => {
    expect(weekdayShort("2026-09-28", "ru")).toBe("пн");
    expect(weekdayShort("2026-09-28", "en")).toBe("Mon");
    expect(rangeLabel("2026-09-28", "2026-10-04", "ru")).toBe("28 сент. – 4 окт.");
    expect(monthTitle("2026-09-15", "ru")).toBe("Сентябрь 2026");
    expect(monthTitle("2026-09-15", "en")).toBe("September 2026");
  });
});
