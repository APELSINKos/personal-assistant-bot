/**
 * Days and wall clocks of a zone, as core/timeutil.py counts them: the server shows everything on
 * the user's city clock. A day is «2026-10-07», a clock «18:30», a moment milliseconds since the
 * epoch. The demo's clock itself, Moscow's, is in clock.ts.
 */
import { addDaysIso, parseIsoDate } from "../../lib/format";

export const MINUTE = 60_000;
export const HOUR = 60 * MINUTE;
export const DAY = 24 * HOUR;

/** A moment as a zone's wall clock shows it. */
export interface Wall {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

const pad = (value: number) => String(value).padStart(2, "0");
const formats = new Map<string, Intl.DateTimeFormat>();

export function wall(zone: string, moment: number): Wall {
  let format = formats.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-US", {
      timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    formats.set(zone, format);
  }
  const parts: Record<string, number> = {};
  for (const part of format.formatToParts(moment)) parts[part.type] = Number(part.value);
  return {
    year: parts.year ?? 0, month: parts.month ?? 0, day: parts.day ?? 0,
    hour: (parts.hour ?? 0) % 24, minute: parts.minute ?? 0, second: parts.second ?? 0,
  };
}

export const dayOf = (at: Wall): string => `${at.year}-${pad(at.month)}-${pad(at.day)}`;
export const clockOf = (at: Wall): string => `${pad(at.hour)}:${pad(at.minute)}`;

/** The day a moment falls on in a zone. */
export const localDay = (zone: string, moment: number): string => dayOf(wall(zone, moment));

/** The time a moment shows in a zone. */
export const localClock = (zone: string, moment: number): string => clockOf(wall(zone, moment));

/** How far a zone's clock is ahead of UTC at a moment. */
function offsetOf(zone: string, moment: number): number {
  const at = wall(zone, moment);
  return Date.UTC(at.year, at.month - 1, at.day, at.hour, at.minute, at.second) - Math.floor(moment / 1000) * 1000;
}

/** The moment of a wall time in a zone: «2026-10-07», «18:30». */
export function momentOf(zone: string, day: string, clock = "00:00"): number {
  const [hour = 0, minute = 0] = clock.split(":").map(Number);
  const guess = parseIsoDate(day).getTime() + hour * HOUR + minute * MINUTE;
  return guess - offsetOf(zone, guess - offsetOf(zone, guess));
}

/** A day's whole span of moments on a zone's clock: [its midnight, the next one). */
export function dayBounds(day: string, zone: string): [number, number] {
  return [momentOf(zone, day), momentOf(zone, addDaysIso(day, 1))];
}

/** A moment as the API writes a datetime: in UTC, to the second. */
export const utc = (moment: number): string => new Date(moment).toISOString().replace(/\.\d{3}Z$/, "Z");

/** 0 for Monday, 6 for Sunday. */
export const weekdayOf = (day: string): number => (parseIsoDate(day).getUTCDay() + 6) % 7;

/** The days of the month a day is in. */
export const monthLength = (day: string): number =>
  new Date(Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)), 0)).getUTCDate();

/** The first day of the month a day is in. */
export const monthStart = (day: string): string => `${day.slice(0, 7)}-01`;

/** The first day of the next month. */
export const nextMonth = (day: string): string => monthStart(addDaysIso(monthStart(day), 32));

/** timeutil.parse_hhmm: «8:5» is «08:05»; null for what is not a time of day. */
export function parseClock(text: string): string | null {
  const found = /^\s*(\d{1,2}):(\d{1,2})\s*$/.exec(text);
  if (!found) return null;
  const [hours, minutes] = [Number(found[1]), Number(found[2])];
  if (hours > 23 || minutes > 59) return null;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

/** Whether the zone is one the server knows (timeutil.is_valid_timezone). */
export function validZone(name: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: name });
    return true;
  } catch {
    return false;
  }
}

/** A real day written as «YYYY-MM-DD». */
export function realDay(text: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(text) && parseIsoDate(text).toISOString().slice(0, 10) === text;
}
