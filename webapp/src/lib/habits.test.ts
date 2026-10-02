import { describe, expect, it } from "vitest";
import { COLORS, dayState, EMOJI, monthOfWeek, nextDone, stateOn, withMark, yearWeeks } from "./habits";

const FROM = "2025-09-29"; // a Monday
// 371 days; the last week (from Monday 28 September 2026): before the habit, then done, missed,
// no mark, done, missed, and Sunday ahead.
const YEAR = ".".repeat(365) + "10-10" + ".";

describe("habit look", () => {
  it("has the server's 32 emoji and 8 colours", () => {
    expect(EMOJI).toHaveLength(32);
    expect(new Set(EMOJI).size).toBe(32);
    expect(COLORS).toEqual(["mint", "sky", "violet", "rose", "coral", "amber", "sand", "slate"]);
  });
});

describe("year map", () => {
  it("reads each day's character", () => {
    expect([dayState("1"), dayState("0"), dayState("-"), dayState("."), dayState(undefined)]).toEqual([
      "done", "missed", "none", "outside", "outside",
    ]);
  });

  it("lays the year out in weeks from Monday", () => {
    const weeks = yearWeeks(FROM, YEAR);
    expect(weeks).toHaveLength(53);
    expect(weeks.every((week) => week.length === 7)).toBe(true);
    expect(weeks[0]?.[0]).toEqual({ iso: "2025-09-29", state: "outside" });
    expect(weeks[52]?.map((day) => day.state)).toEqual([
      "outside", "done", "missed", "none", "done", "missed", "outside",
    ]);
    expect(weeks[52]?.[6]?.iso).toBe("2026-10-04");
  });

  it("finds a day's state by its date", () => {
    expect(stateOn(FROM, YEAR, "2026-09-29")).toBe("done");
    expect(stateOn(FROM, YEAR, "2026-10-01")).toBe("none");
    expect(stateOn(FROM, YEAR, "2025-09-28")).toBe("outside"); // before the map
  });

  it("changes one day's mark and never a day outside the habit", () => {
    expect(withMark(FROM, YEAR, "2026-10-01", true).slice(365, 370)).toBe("10110");
    expect(withMark(FROM, YEAR, "2026-09-29", null).slice(365, 370)).toBe("-0-10");
    expect(withMark(FROM, YEAR, "2026-09-28", true)).toBe(YEAR); // «.»: before the habit
    expect(withMark(FROM, YEAR, "2027-01-01", true)).toBe(YEAR); // past the map
  });

  it("cycles a tap: no mark, done, missed", () => {
    expect([nextDone("none"), nextDone("done"), nextDone("missed")]).toEqual([true, false, null]);
  });
});

describe("the month a week opens", () => {
  it("is the month that holds most of the week: its Thursday's", () => {
    expect(monthOfWeek("2026-08-31", "2026-10-02", "2025-06-02")).toBe("2026-09-01"); // Thu 3 Sep
    expect(monthOfWeek("2026-09-28", "2026-11-20", "2025-06-02")).toBe("2026-10-01"); // Thu 1 Oct
  });

  it("is this month for this week, so today is in view", () => {
    expect(monthOfWeek("2026-09-28", "2026-10-02", "2025-06-02")).toBe("2026-10-01"); // Fri 2 Oct
    expect(monthOfWeek("2026-10-26", "2026-11-01", "2025-06-02")).toBe("2026-11-01"); // Sun 1 Nov
    expect(monthOfWeek("2026-09-28", "2026-09-30", "2025-06-02")).toBe("2026-09-01"); // Wed 30 Sep
  });

  it("is never a month before the habit's first day", () => {
    expect(monthOfWeek("2026-08-24", "2026-10-02", "2026-09-14")).toBe("2026-09-01");
  });
});
