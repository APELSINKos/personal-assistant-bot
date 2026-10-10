import { describe, expect, it } from "vitest";
import {
  clockOf, localDay, momentOf, monthLength, utc, validZone, wall, weekdayOf,
} from "./time";

// Wednesday 7 October 2026, 10:30 in Moscow.
const MORNING = Date.UTC(2026, 9, 7, 7, 30);

describe("the clock of a zone", () => {
  it("reads a moment on a city's wall clock", () => {
    expect(wall("Europe/Moscow", MORNING)).toEqual({ year: 2026, month: 10, day: 7, hour: 10, minute: 30, second: 0 });
    expect(clockOf(wall("Asia/Kamchatka", MORNING))).toBe("19:30");
    expect(localDay("Asia/Kamchatka", Date.UTC(2026, 9, 7, 13, 0))).toBe("2026-10-08");
    expect(localDay("Europe/London", Date.UTC(2026, 9, 6, 23, 30))).toBe("2026-10-07");
  });

  it("finds the moment of a wall time, across a change of the clocks too", () => {
    expect(momentOf("Europe/Moscow", "2026-10-07", "10:30")).toBe(MORNING);
    expect(momentOf("Asia/Kamchatka", "2026-10-08", "00:00")).toBe(Date.UTC(2026, 9, 7, 12, 0));
    // London is on summer time until 25 October 2026, on winter time after.
    expect(momentOf("Europe/London", "2026-10-24", "12:00")).toBe(Date.UTC(2026, 9, 24, 11, 0));
    expect(momentOf("Europe/London", "2026-10-26", "12:00")).toBe(Date.UTC(2026, 9, 26, 12, 0));
  });

  it("writes a moment as the API does, in UTC to the second", () => {
    expect(utc(MORNING + 1234)).toBe("2026-10-07T07:30:01Z");
  });

  it("knows the days of the calendar", () => {
    expect(weekdayOf("2026-10-05")).toBe(0);
    expect(weekdayOf("2026-10-11")).toBe(6);
    expect(monthLength("2026-02-10")).toBe(28);
    expect(monthLength("2028-02-01")).toBe(29);
    expect(monthLength("2026-10-31")).toBe(31);
  });

  it("knows the zones the server knows", () => {
    expect(validZone("Asia/Yerevan")).toBe(true);
    expect(validZone("Mars/Olympus")).toBe(false);
    expect(validZone("")).toBe(false);
  });
});
