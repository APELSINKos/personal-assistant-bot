import type { HabitColor } from "../api/types";
import { addDaysIso, daysBetween } from "./format";

/** A daily habit's weekly goal. */
export const DAILY = 7;

/** The emoji a habit can have — the same set as the server's (assistant/core/habit_style.py). */
export const EMOJI = [
  "💪", "🏃", "🚴", "🏊", "🧘", "🚶", "⚽", "🎾",
  "💧", "🥗", "🍎", "💊", "😴", "🦷", "🚭", "☕",
  "📚", "🧠", "💻", "🎸", "🎨", "📝", "🌍", "🎓",
  "🧹", "🌱", "🐕", "💰", "📵", "🙏", "🌅", "🎯",
] as const;

/** The palette, in the server's order; each is a CSS token per theme (--habit-mint …). */
export const COLORS: readonly HabitColor[] = [
  "mint", "sky", "violet", "rose", "coral", "amber", "sand", "slate",
];

export type DayState = "done" | "missed" | "none" | "outside";

const STATES: Record<string, DayState> = { "1": "done", "0": "missed", "-": "none" };
const CHARS: Record<"done" | "missed" | "none", string> = { done: "1", missed: "0", none: "-" };

/** A day of a habit's year or week string («1» done, «0» missed, «-» no mark, «.» outside). */
export function dayState(char: string | undefined): DayState {
  return (char !== undefined && STATES[char]) || "outside";
}

export interface YearDay {
  iso: string;
  state: DayState;
}

/** The year map: one column per week (Monday first), from `from`, as many weeks as `year` has. */
export function yearWeeks(from: string, year: string): YearDay[][] {
  const weeks: YearDay[][] = [];
  for (let start = 0; start < year.length; start += 7) {
    weeks.push(
      Array.from({ length: 7 }, (_, day) => ({
        iso: addDaysIso(from, start + day),
        state: dayState(year[start + day]),
      })),
    );
  }
  return weeks;
}

/** The state of `iso` in a year string starting on `from` («outside» beyond it). */
export function stateOn(from: string, year: string, iso: string): DayState {
  const index = daysBetween(from, iso);
  return index < 0 ? "outside" : dayState(year[index]);
}

/** The year string with the mark of `iso` changed, for showing a tap before the server answers. */
export function withMark(from: string, year: string, iso: string, done: boolean | null): string {
  const index = daysBetween(from, iso);
  if (index < 0 || index >= year.length || year[index] === ".") return year;
  const char = CHARS[done === true ? "done" : done === false ? "missed" : "none"];
  return year.slice(0, index) + char + year.slice(index + 1);
}

/** The next mark of a tap: no mark → done → missed → no mark. */
export function nextDone(state: DayState): boolean | null {
  if (state === "none") return true;
  return state === "done" ? false : null;
}
