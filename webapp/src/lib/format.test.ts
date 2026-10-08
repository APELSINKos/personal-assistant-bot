import { describe, expect, it } from "vitest";
import {
  addDaysIso, bigDate, clip, codePoints, dayHeading, dayMonth, daysBetween, formatNumber, formatRange, formatTemp,
  lessonMeta, localTimeHm, localTodayIso, monthGrid, monthTitle, rangeLabel, shortMoment, shownChance, weekOf,
  weekdayShort,
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

  it("writes a day's range with the degree sign once", () => {
    expect(formatRange(1.6, 7.2)).toBe("+2…+7°");
    expect(formatRange(-4.2, 0.3)).toBe("-4…0°");
    expect(formatRange(null, 7)).toBe("—…+7°");
  });

  it("mentions a chance of precipitation from 20 %, or from the threshold it is given", () => {
    expect([null, 0, 19, 20, 80].map((chance) => shownChance(chance))).toEqual([null, null, null, 20, 80]);
    // The way to classes: the server sends nothing under 30 % there, and the app holds to it too.
    expect([null, 29, 30, 70].map((chance) => shownChance(chance, 30))).toEqual([null, null, 30, 70]);
  });

  it("does date arithmetic in the city's zone", () => {
    expect(addDaysIso("2026-12-31", 1)).toBe("2027-01-01");
    const late = new Date("2026-09-28T22:30:00Z");
    expect(localTodayIso("Europe/Moscow", late)).toBe("2026-09-29");
    expect(localTodayIso("UTC", late)).toBe("2026-09-28");
    expect(localTimeHm("Europe/Moscow", late)).toBe("01:30");
  });

  it("names a day with its month, and with its year when asked", () => {
    expect(dayMonth("2026-09-28", "ru")).toBe("28 сентября");
    expect(dayMonth("2026-09-28", "en")).toBe("September 28");
    expect(dayMonth("2025-06-02", "ru", true)).toBe("2 июня 2025");
    expect(dayMonth("2025-06-02", "en", true)).toBe("June 2, 2025");
  });

  it("counts a text in code points, as the server does", () => {
    expect(codePoints("")).toBe(0);
    expect(codePoints("Straße")).toBe(6);
    expect(codePoints("😀")).toBe(1); // two UTF-16 units
    expect("😀".repeat(300)).toHaveLength(600);
    expect(codePoints("😀".repeat(300))).toBe(300); // a note of 300 emoji fits in 500
    // As Python's len(): a family is five code points, a flag two, «й» written as «и» and a breve two.
    expect(codePoints(String.fromCodePoint(0x1f468, 0x200d, 0x1f469, 0x200d, 0x1f467))).toBe(5);
    expect(codePoints("🇷🇺")).toBe(2);
    expect(codePoints(String.fromCharCode(0x438, 0x306))).toBe(2);
  });

  it("clips a text to quote at 60 code points, the last of them «…»", () => {
    expect(clip("Таблетки")).toBe("Таблетки");
    expect(clip("а".repeat(60))).toBe("а".repeat(60));
    expect(clip("а".repeat(61))).toBe(`${"а".repeat(59)}…`);
    expect(clip("💊".repeat(300))).toBe(`${"💊".repeat(59)}…`); // an emoji is one, never half of one
    expect(clip(`${"а".repeat(58)} ${"б".repeat(10)}`)).toBe(`${"а".repeat(58)}…`); // no space before «…»
    expect(clip("Купить молоко", 8)).toBe("Купить…");
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

  it("describes a lesson with whatever it has", () => {
    expect(lessonMeta("ЛК", "10:40", "12:10", "А-16")).toBe("ЛК · 10:40–12:10 · А-16");
    expect(lessonMeta(null, "10:40", "12:10", null)).toBe("10:40–12:10");
  });

  it("gives a lesson that ends when it starts (no DTEND) its start only", () => {
    expect(lessonMeta("ЛК", "12:40", "12:40", null)).toBe("ЛК · 12:40");
    expect(lessonMeta(null, "12:40", "12:40", "А-16")).toBe("12:40 · А-16");
  });

  it("shows a moment in the city's zone", () => {
    expect(shortMoment("2026-09-28T12:00:00Z", "Europe/Moscow", "ru")).toBe("28 сент., 15:00");
    expect(shortMoment("2026-09-28T12:00:00Z", "Asia/Vladivostok", "en")).toBe("Sep 28, 22:00");
  });
});
