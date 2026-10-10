/**
 * The repeats of reminders (core/services/recurrence.py): which local days a rule fires on and at
 * which moments, counted on the user's calendar and only then turned into moments.
 */
import type { RepeatRule } from "../../api/types";
import type { Lang } from "../../i18n";
import { addDaysIso, daysBetween, mondayOf } from "../../lib/format";
import { invalidInput } from "./http";
import { localDay, momentOf, monthLength, parseClock, weekdayOf } from "./time";
import { TEXTS } from "./words";

/** Weekday bits: Monday 1, Tuesday 2 … Sunday 64. */
export const ALL_DAYS = 0b1111111;
export const WEEKDAYS = 0b0011111;
export const WEEKENDS = 0b1100000;
/** How far a rule is walked to find its next firing: a valid one fires within two months. */
const HORIZON = 400;

const repeatInvalid = () => invalidInput({ field: "repeat", reason: "repeat_invalid" });

/** Rule.validate: a rule the calendar can walk, else repeat_invalid. */
export function validateRule(rule: RepeatRule): void {
  if (parseClock(rule.time_local) !== rule.time_local) throw repeatInvalid();
  if (rule.repeat === "weekly") {
    if (rule.weekdays === null || rule.weekdays < 1 || rule.weekdays > ALL_DAYS) throw repeatInvalid();
    if (rule.interval_weeks !== 1 && rule.interval_weeks !== 2) throw repeatInvalid();
  } else if (rule.repeat === "monthly") {
    if (rule.month_day === null || rule.month_day < 1 || rule.month_day > 31) throw repeatInvalid();
  }
}

export function firesOn(rule: RepeatRule, day: string): boolean {
  if (day < rule.anchor_date) return false;
  if (rule.repeat === "daily") return true;
  if (rule.repeat === "weekly") {
    if (rule.weekdays === null || !(rule.weekdays & (1 << weekdayOf(day)))) return false;
    const weeks = daysBetween(mondayOf(rule.anchor_date), mondayOf(day)) / 7;
    return weeks % rule.interval_weeks === 0;
  }
  return rule.month_day !== null && Number(day.slice(8)) === Math.min(rule.month_day, monthLength(day));
}

/** The moment of the rule's firing on a local day. */
export const momentOn = (rule: RepeatRule, day: string, zone: string): number => momentOf(zone, day, rule.time_local);

/** The days the rule fires on from `start` (or its anchor, if later) to `end`. */
function* localDays(rule: RepeatRule, start: string, end: string): Generator<string> {
  for (let day = start > rule.anchor_date ? start : rule.anchor_date; day <= end; day = addDaysIso(day, 1)) {
    if (firesOn(rule, day)) yield day;
  }
}

/** The first firing strictly after a moment; repeat_invalid for a rule that never fires. */
export function nextAfter(rule: RepeatRule, after: number, zone: string): number {
  const start = addDaysIso(localDay(zone, after), -1);
  for (const day of localDays(rule, start, addDaysIso(start, HORIZON))) {
    const moment = momentOn(rule, day, zone);
    if (moment > after) return moment;
  }
  throw repeatInvalid();
}

/** The firings in [start, end). */
export function between(rule: RepeatRule, start: number, end: number, zone: string): number[] {
  const found: number[] = [];
  for (const day of localDays(rule, addDaysIso(localDay(zone, start), -1), localDay(zone, end))) {
    const moment = momentOn(rule, day, zone);
    if (start <= moment && moment < end) found.push(moment);
  }
  return found;
}

/**
 * The first day from `start`, within two weeks, of the rule's weekdays (every week) whose firing
 * comes after the wall time `after` («2026-10-07T10:30»); null for a rule without weekdays.
 */
export function firstMatchingDay(rule: RepeatRule, start: string, after: string): string | null {
  const weekly = { ...rule, interval_weeks: 1 };
  for (let offset = 0; offset < 14; offset += 1) {
    const day = addDaysIso(start, offset);
    if (firesOn(weekly, day) && `${day}T${rule.time_local}` > after) return day;
  }
  return null;
}

/** «по будням в 09:00», «вт, чт в 10:40», «каждый месяц 5-го в 12:00». */
export function describeRule(rule: RepeatRule, lang: Lang): string {
  const words = TEXTS[lang].repeat;
  if (rule.repeat === "daily") return words.daily(rule.time_local);
  if (rule.repeat === "monthly") return words.monthly(rule.month_day ?? 1, rule.time_local);
  const bits = rule.weekdays ?? 0;
  if (rule.interval_weeks === 1 && bits === WEEKDAYS) return words.weekdays(rule.time_local);
  if (rule.interval_weeks === 1 && bits === WEEKENDS) return words.weekends(rule.time_local);
  const days = TEXTS[lang].days.filter((_, index) => bits & (1 << index)).join(", ");
  return rule.interval_weeks === 2 ? words.biweekly(days, rule.time_local) : words.weekly(days, rule.time_local);
}
