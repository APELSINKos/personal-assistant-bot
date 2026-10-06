import { describe, expect, it } from "vitest";
import type { ClassesWeather, TodayLesson } from "../api/types";
import { dict } from "../i18n";
import { forecast } from "../test/fixtures";
import { NBSP } from "./money";
import {
  CELL_WIDTH, CURVE_HEIGHT, classesLine, nextClassesChange, rangeBar, smoothPath, stripCells, temperatureCurve,
  weekDayLabel, weekDayName, windWords,
} from "./weather";

/** Every y of a path's points and control points. */
function ys(path: string): number[] {
  return [...path.matchAll(/-?[\d.]+,(-?[\d.]+)/g)].map((match) => Number(match[1]));
}

describe("the 24-hour strip", () => {
  it("starts with now, then the hours after it", () => {
    const cells = stripCells(forecast, "Сейчас");
    expect(cells).toHaveLength(24);
    expect(cells[0]).toEqual({
      time: "Сейчас", emoji: "🌤", description: "малооблачно", temperature: 9.6, chance: 0,
    });
    expect(cells[1]).toEqual({ time: "16:00", emoji: "🌤", description: "малооблачно", temperature: 13.0, chance: 0 });
    expect(cells[6]).toMatchObject({ time: "21:00", emoji: "🌙", chance: 40 });
    expect(cells.at(-1)?.time).toBe("14:00");
  });

  it("draws a straight piece between two points", () => {
    expect(smoothPath([])).toBe("");
    expect(smoothPath([[26, 20]])).toBe("M26,20");
    expect(smoothPath([[0, 0], [30, 30]])).toBe("M0,0 C10,10 20,20 30,30");
  });

  it("lies flat at a peak and never swings past the points", () => {
    expect(smoothPath([[0, 10], [10, 0], [20, 10]])).toBe("M0,10 C3.3,6.7 6.7,0 10,0 C13.3,0 16.7,6.7 20,10");
    // A step: a curve through it that overshot would show a warmth no hour has.
    const step = smoothPath([[0, 0], [10, 0], [20, 10], [30, 10], [40, 10]]);
    expect(Math.min(...ys(step))).toBe(0);
    expect(Math.max(...ys(step))).toBe(10);
  });

  it("puts the warmest hour at the top and each point over the middle of its cell", () => {
    const curve = temperatureCurve([9.6, 13.0, 5.8]);
    expect(curve).toMatchObject({ low: 5.8, high: 13.0 });
    // 6 px of room over the warmest and under the coldest of the 40.
    expect(curve?.points).toEqual([[26, expect.closeTo(19.2, 1)], [78, 6], [130, 34]]);
    expect(curve?.points[1]?.[0]).toBe(CELL_WIDTH * 1.5);
    expect(curve?.line.startsWith("M26,")).toBe(true);
    expect(curve?.area.endsWith(` L130,${CURVE_HEIGHT} L26,${CURVE_HEIGHT} Z`)).toBe(true);
  });

  it("leaves out a cell without a temperature, and draws nothing under two", () => {
    const curve = temperatureCurve([null, 7, 8]);
    expect(curve?.points[0]).toBeNull();
    expect(curve?.line.startsWith("M78,")).toBe(true);
    expect(temperatureCurve([null, 7])).toBeNull();
    expect(temperatureCurve([])).toBeNull();
    // The same temperature all day: a flat line across the middle.
    expect(temperatureCurve([4, 4, 4])?.points).toEqual([[26, 20], [78, 20], [130, 20]]);
  });
});

describe("the week", () => {
  const words = { today: "Сегодня", tomorrow: "Завтра" };

  it("names the first day today and the next tomorrow, the others by their date", () => {
    expect(weekDayLabel(0, "2026-09-28", "ru", words)).toBe("Сегодня");
    expect(weekDayLabel(1, "2026-09-29", "ru", words)).toBe("Завтра");
    expect(weekDayLabel(2, "2026-09-30", "ru", words)).toBe("ср, 30 сент.");
    expect(weekDayLabel(2, "2026-10-07", "ru", words)).toBe("ср, 7 окт.");
    expect(weekDayLabel(2, "2026-09-30", "en", { today: "Today", tomorrow: "Tomorrow" })).toBe("Wed, Sep 30");
  });

  it("says a day in full for a screen reader", () => {
    expect(weekDayName(0, "2026-09-28", "ru", words)).toBe("Сегодня");
    expect(weekDayName(2, "2026-10-07", "ru", words)).toBe("Среда, 7 октября");
    expect(weekDayName(2, "2026-10-07", "en", words)).toBe("Wednesday, October 7");
  });

  it("places a day's range on the week's scale", () => {
    expect(rangeBar(5, 10, 0, 20)).toEqual({ from: 25, width: 25 });
    expect(rangeBar(3.2, 14.1, 3.2, 14.1)).toEqual({ from: 0, width: 100 });
    expect(rangeBar(6.1, 11.0, 3.2, 14.1)).toEqual({ from: 26.6, width: 45 });
    expect(rangeBar(4, 4, 4, 4)).toEqual({ from: 0, width: 100 }); // one temperature all week
  });
});

describe("the wind", () => {
  it("names the gusts only when they blow harder than the wind", () => {
    expect(windWords(3.4, 6.1)).toEqual({ speed: "3", gusts: "6" });
    expect(windWords(3.4, 3.2)).toEqual({ speed: "3", gusts: null });
    expect(windWords(3.4, null)).toEqual({ speed: "3", gusts: null });
    expect(windWords(null, 6.1)).toBeNull();
  });
});

describe("the weather of the way to classes", () => {
  const t = dict("ru");
  // 10:40–12:10 and 12:40–14:10 in Moscow.
  const lessons: TodayLesson[] = [
    {
      time: "10:40", end: "12:10", title: "Матанализ", kind: "ЛК", room: null,
      starts_at: "2026-09-28T07:40:00Z", ends_at: "2026-09-28T09:10:00Z",
    },
    {
      time: "12:40", end: "14:10", title: "Базы данных", kind: "ПР", room: null,
      starts_at: "2026-09-28T09:40:00Z", ends_at: "2026-09-28T11:10:00Z",
    },
  ];
  const weather: ClassesWeather = {
    start: "10:40", start_temp: 8.2, start_chance: 40, end: "14:10", end_temp: 11.6, end_chance: null,
  };
  const at = (iso: string) => Date.parse(iso);

  it("tells the way there and back before the first class", () => {
    expect(classesLine(weather, lessons, t, at("2026-09-28T07:00:00Z"))).toBe(
      `🎓 На пары (10:40): +8°, 💧${NBSP}40${NBSP}% · после пар (14:10): +12°`,
    );
    expect(classesLine(weather, lessons, dict("en"), at("2026-09-28T07:00:00Z"))).toBe(
      `🎓 To classes (10:40): +8°, 💧${NBSP}40% · after (14:10): +12°`,
    );
  });

  it("tells only the way back once the first class has begun", () => {
    expect(classesLine(weather, lessons, t, at("2026-09-28T07:40:00Z"))).toBe("🎓 После пар (14:10): +12°");
    expect(classesLine({ ...weather, end_chance: 70 }, lessons, t, at("2026-09-28T10:00:00Z"))).toBe(
      `🎓 После пар (14:10): +12°, 💧${NBSP}70${NBSP}%`,
    );
  });

  it("tells nothing after the last class", () => {
    expect(classesLine(weather, lessons, t, at("2026-09-28T11:10:00Z"))).toBeNull();
  });

  it("leaves out the way there without its forecast, and everything without the forecast of the end", () => {
    const before = at("2026-09-28T07:00:00Z");
    expect(classesLine({ ...weather, start_temp: null }, lessons, t, before)).toBe("🎓 После пар (14:10): +12°");
    expect(classesLine({ ...weather, end_temp: null }, lessons, t, before)).toBeNull();
    expect(classesLine(null, lessons, t, before)).toBeNull();
    expect(classesLine(weather, [], t, before)).toBeNull();
  });

  it("names a chance from 30 %", () => {
    const line = classesLine({ ...weather, start_chance: 29, end_chance: 30 }, lessons, t, at("2026-09-28T07:00:00Z"));
    expect(line).toBe(`🎓 На пары (10:40): +8° · после пар (14:10): +12°, 💧${NBSP}30${NBSP}%`);
  });

  it("knows when the card changes next: the first start, then the last end", () => {
    expect(nextClassesChange(lessons, at("2026-09-28T07:00:00Z"))).toBe(at("2026-09-28T07:40:00Z"));
    expect(nextClassesChange(lessons, at("2026-09-28T07:40:00Z"))).toBe(at("2026-09-28T11:10:00Z"));
    expect(nextClassesChange(lessons, at("2026-09-28T11:10:00Z"))).toBeNull();
    expect(nextClassesChange([], at("2026-09-28T07:00:00Z"))).toBeNull();
  });
});
