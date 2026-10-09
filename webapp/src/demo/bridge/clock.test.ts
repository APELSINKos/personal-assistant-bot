import { describe, expect, it, vi } from "vitest";
import { installClock, shiftedDate } from "./clock";

const NOW = Date.UTC(2026, 9, 9, 12, 0);
const HOUR = 3_600_000;

describe("the demo's Date in the frame", () => {
  it("runs ahead of the real clock by the offset, and goes on", () => {
    vi.useFakeTimers({ now: NOW });
    const DemoDate = shiftedDate(HOUR);
    expect(new DemoDate().getTime()).toBe(NOW + HOUR);
    expect(DemoDate.now()).toBe(NOW + HOUR);
    vi.advanceTimersByTime(60_000);
    expect(DemoDate.now()).toBe(NOW + HOUR + 60_000);
  });

  it("makes any other date as Date does", () => {
    const DemoDate = shiftedDate(HOUR);
    expect(new DemoDate(2026, 9, 7, 10, 30).getTime()).toBe(new Date(2026, 9, 7, 10, 30).getTime());
    expect(new DemoDate("2026-10-07T07:30:00Z").toISOString()).toBe("2026-10-07T07:30:00.000Z");
    expect(new DemoDate(0).getTime()).toBe(0);
  });

  it("gives its time as a string when called without new, as Date does", () => {
    vi.useFakeTimers({ now: NOW });
    const DemoDate = shiftedDate(HOUR);
    expect(DemoDate()).toBe(new Date(NOW + HOUR).toString());
  });

  it("is a Date to instanceof and keeps parse and UTC", () => {
    const DemoDate = shiftedDate(HOUR);
    expect(new DemoDate()).toBeInstanceOf(Date);
    expect(new Date()).toBeInstanceOf(DemoDate);
    expect(DemoDate.UTC(2026, 9, 7)).toBe(Date.UTC(2026, 9, 7));
    expect(DemoDate.parse("2026-10-07T07:30:00Z")).toBe(Date.parse("2026-10-07T07:30:00Z"));
  });

  it("goes in only with an offset", () => {
    const real = window.Date;
    try {
      installClock(null);
      expect(window.Date).toBe(real);
      installClock(HOUR);
      expect(window.Date).not.toBe(real);
      expect(window.Date.now() - real.now()).toBeGreaterThanOrEqual(HOUR - 1_000);
    } finally {
      window.Date = real;
    }
  });
});
