import { describe, expect, it } from "vitest";
import { moscowDay, moscowHour, parseAt } from "./clock";

describe("the demo's clock", () => {
  it("reads ?at= as a moment on Moscow's clock", () => {
    expect(parseAt("2026-10-07T10:30")).toBe(Date.UTC(2026, 9, 7, 7, 30));
    expect(parseAt("2026-01-01T00:00")).toBe(Date.UTC(2025, 11, 31, 21, 0));
  });

  it("ignores an ?at= that names no real moment", () => {
    const wrong = [
      null, "", "2026-10-07", "2026-10-07T10:30:00", "2026-10-07 10:30", "2026-10-07T24:00", "2026-10-07T10:60",
      "2026-02-30T10:00", "2026-13-01T10:00", "2026-1-7T10:30", " 2026-10-07T10:30", "2026-10-07T10:30Z",
    ];
    for (const value of wrong) expect(parseAt(value), String(value)).toBeNull();
  });

  it("tells the day and the hour in Moscow", () => {
    const night = Date.UTC(2026, 9, 6, 21, 30); // 00:30 on October 7 in Moscow
    expect(moscowDay(night)).toBe("2026-10-07");
    expect(moscowHour(night)).toBe(0);
    expect(moscowHour(Date.UTC(2026, 9, 7, 7, 30))).toBe(10);
  });
});
