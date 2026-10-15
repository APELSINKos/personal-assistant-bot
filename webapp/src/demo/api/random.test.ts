import { describe, expect, it } from "vitest";
import { chance, draws, fnv1a, mulberry32 } from "./random";

describe("the demo's chance", () => {
  it("hashes a text with FNV-1a", () => {
    expect(fnv1a("")).toBe(0x811c9dc5);
    expect(fnv1a("a")).toBe(0xe40c292c);
    expect(fnv1a("foobar")).toBe(0xbf9cf968);
  });

  it("draws numbers in [0, 1) with mulberry32, the same ones for the same seed", () => {
    const first = mulberry32(42);
    const again = mulberry32(42);
    const numbers = Array.from({ length: 1000 }, () => first());
    expect(Array.from({ length: 1000 }, () => again())).toEqual(numbers);
    expect(numbers.every((value) => value >= 0 && value < 1)).toBe(true);
    // Spread over the whole range, not stuck in a corner of it.
    expect(Math.min(...numbers)).toBeLessThan(0.01);
    expect(Math.max(...numbers)).toBeGreaterThan(0.99);
    expect(numbers.reduce((sum, value) => sum + value, 0) / numbers.length).toBeCloseTo(0.5, 1);
  });

  it("gives a thing its own numbers: the same parts, the same draws", () => {
    const day = draws("2026-10-07", "ru", "money");
    const sameDay = draws("2026-10-07", "ru", "money");
    expect([day(), day(), day()]).toEqual([sameDay(), sameDay(), sameDay()]);
    expect(chance("2026-10-07", "ru", "money")).toBe(draws("2026-10-07", "ru", "money")());
    expect(chance("2026-10-08", "ru", "money")).not.toBe(chance("2026-10-07", "ru", "money"));
    expect(chance("2026-10-07", "en", "money")).not.toBe(chance("2026-10-07", "ru", "money"));
    expect(chance("2026-10-07", "ru", "habit", 1)).not.toBe(chance("2026-10-07", "ru", "habit", 2));
  });
});
