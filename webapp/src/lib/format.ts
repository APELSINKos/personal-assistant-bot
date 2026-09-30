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

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function shortDay(iso: string, lang: Lang): string {
  const text = new Intl.DateTimeFormat(lang, {
    timeZone: "UTC", weekday: "short", day: "numeric", month: "short",
  }).format(parseIsoDate(iso));
  return capitalize(text);
}

export function timeOf(dueLocal: string): string {
  return dueLocal.slice(11, 16);
}

export interface DayGroup<T> {
  day: string;
  label: string;
  items: T[];
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

export function rangeLabel(fromIso: string, toIso: string, lang: Lang): string {
  const format = new Intl.DateTimeFormat(lang, { timeZone: "UTC", day: "numeric", month: "short" });
  return `${format.format(parseIsoDate(fromIso))} – ${format.format(parseIsoDate(toIso))}`;
}

export function monthTitle(iso: string, lang: Lang): string {
  const date = parseIsoDate(iso);
  const month = new Intl.DateTimeFormat(lang, { timeZone: "UTC", month: "long" }).format(date);
  return capitalize(`${month} ${date.getUTCFullYear()}`);
}

export function groupByDay<T extends { due_local: string }>(
  items: readonly T[],
  todayIso: string,
  lang: Lang,
  labels: { today: string; tomorrow: string },
): DayGroup<T>[] {
  const tomorrow = addDaysIso(todayIso, 1);
  const byDay = new Map<string, T[]>();
  for (const item of [...items].sort((a, b) => a.due_local.localeCompare(b.due_local))) {
    const day = item.due_local.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), item]);
  }
  return [...byDay.entries()].map(([day, dayItems]) => ({
    day,
    items: dayItems,
    label: day === todayIso ? labels.today : day === tomorrow ? labels.tomorrow : shortDay(day, lang),
  }));
}
