import type { Lang } from "../i18n";

/** A calendar date "YYYY-MM-DD" as a Date at UTC midnight (format with timeZone "UTC"). */
export function parseIsoDate(iso: string): Date {
  const [year = 1970, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function addDaysIso(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function localTodayIso(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
}

export function localTimeHm(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(now);
}

export interface BigDate {
  day: string;
  weekday: string;
  month: string;
  year: string;
}

export function bigDate(iso: string, lang: Lang): BigDate {
  const date = parseIsoDate(iso);
  const part = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(lang, { timeZone: "UTC", ...options }).format(date);
  return {
    day: String(date.getUTCDate()),
    weekday: part({ weekday: "long" }),
    month: part({ month: "long" }),
    year: String(date.getUTCFullYear()),
  };
}

export function formatNumber(value: number, lang: Lang, digits = 2): string {
  return new Intl.NumberFormat(lang, {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(value);
}

export function formatTemp(value: number | null): string {
  if (value === null) return "—";
  const rounded = Math.round(value);
  if (rounded === 0) return "0°";
  return rounded > 0 ? `+${rounded}°` : `${rounded}°`;
}

/**
 * A chance of precipitation worth mentioning. Only `shownChance` makes one, and the weather texts
 * of the dictionaries take nothing else: a forecast's raw chance there would read «осадки 0 %».
 */
export type ShownChance = number & { readonly __brand: "ShownChance" };

/**
 * The chance the app mentions, as the bot does: from 20 % — the weather of the way to classes from
 * 30 % — else null, and a lower chance goes unsaid.
 */
export function shownChance(chance: number | null, from = 20): ShownChance | null {
  return chance !== null && chance >= from ? (chance as ShownChance) : null;
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * A text's length as the server measures it, in Unicode code points: an emoji is one, where
 * `length` counts its two UTF-16 halves. Every limit of a form is checked with this.
 */
export function codePoints(text: string): number {
  return [...text].length;
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((parseIsoDate(toIso).getTime() - parseIsoDate(fromIso).getTime()) / 86_400_000);
}

export function mondayOf(iso: string): string {
  const weekday = (parseIsoDate(iso).getUTCDay() + 6) % 7; // Monday = 0
  return addDaysIso(iso, -weekday);
}

export function weekOf(iso: string): string[] {
  const monday = mondayOf(iso);
  return Array.from({ length: 7 }, (_, i) => addDaysIso(monday, i));
}

/** Whole weeks, Monday first, that cover the month of `iso`. */
export function monthGrid(iso: string): string[][] {
  const first = `${iso.slice(0, 8)}01`;
  const month = iso.slice(0, 7);
  const weeks: string[][] = [];
  let start = mondayOf(first);
  while (start.slice(0, 7) <= month || weeks.length === 0) {
    const week = weekOf(start);
    weeks.push(week);
    start = addDaysIso(start, 7);
    if (week[6] !== undefined && week[6].slice(0, 7) > month) break;
  }
  return weeks;
}

export function dayNumber(iso: string): string {
  return String(parseIsoDate(iso).getUTCDate());
}

export function weekdayShort(iso: string, lang: Lang): string {
  const text = new Intl.DateTimeFormat(lang, { timeZone: "UTC", weekday: "short" }).format(parseIsoDate(iso));
  return text.replace(/\.$/, "");
}

interface DayWords {
  today: string;
  tomorrow: string;
  afterTomorrow: string;
  yesterday: string;
}

/** «Сегодня · вторник, 29 сентября», or «Вторник, 6 октября» further away. */
export function dayHeading(iso: string, todayIso: string, lang: Lang, words: DayWords): string {
  const date = parseIsoDate(iso);
  const weekday = new Intl.DateTimeFormat(lang, { timeZone: "UTC", weekday: "long" }).format(date);
  const day = new Intl.DateTimeFormat(lang, { timeZone: "UTC", day: "numeric", month: "long" }).format(date);
  const word = { 0: words.today, 1: words.tomorrow, 2: words.afterTomorrow, [-1]: words.yesterday }[
    daysBetween(todayIso, iso)
  ];
  return word ? `${word} · ${weekday}, ${day}` : capitalize(`${weekday}, ${day}`);
}

/** «28 сентября» / «September 28»; with the year — «28 сентября 2025» / «September 28, 2025». */
export function dayMonth(iso: string, lang: Lang, withYear = false): string {
  const format = new Intl.DateTimeFormat(lang, { timeZone: "UTC", day: "numeric", month: "long" });
  const day = format.format(parseIsoDate(iso));
  if (!withYear) return day;
  // Spelled out rather than Intl's `year` option, which adds «г.» in Russian: the bot and the card
  // write «2 июня 2025».
  return lang === "ru" ? `${day} ${iso.slice(0, 4)}` : `${day}, ${iso.slice(0, 4)}`;
}

export function rangeLabel(fromIso: string, toIso: string, lang: Lang): string {
  const format = new Intl.DateTimeFormat(lang, { timeZone: "UTC", day: "numeric", month: "short" });
  return `${format.format(parseIsoDate(fromIso))} – ${format.format(parseIsoDate(toIso))}`;
}

export function monthTitle(iso: string, lang: Lang): string {
  const date = parseIsoDate(iso);
  const month = new Intl.DateTimeFormat(lang, { timeZone: "UTC", month: "long" }).format(date);
  return capitalize(`${month} ${date.getUTCFullYear()}`);
}

/** «ЛК · 10:40–12:10 · А-16» — a lesson's kind, time and room, whichever it has; only the start
 *  for one that ends when it starts (an event without DTEND or DURATION). */
export function lessonMeta(kind: string | null, time: string, end: string, room: string | null): string {
  return [kind, end === time ? time : `${time}–${end}`, room].filter(Boolean).join(" · ");
}

/** «28 сент., 15:00» — a moment in the city's zone. */
export function shortMoment(iso: string, timeZone: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang, {
    timeZone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(iso));
}
