/**
 * The reminders and the calendar (routers/reminders.py and routers/agenda.py, services/reminders.py):
 * one-off reminders and repeats on the user's clock, edited whole or not at all, and every day of a
 * range with its reminders and lessons. There is no bot here to deliver a reminder: a one-off whose
 * time has come is gone, as the delivered one leaves the list; a repeat goes on to its next time.
 */
import type { Agenda, AgendaItem, ParsedPhrase, Reminder, RepeatRule, RuleInput } from "../../api/types";
import { addDaysIso, codePoints, daysBetween } from "../../lib/format";
import type { StoredReminder, Visit } from "./data";
import { created, invalidInput, json, limitReached, noContent, notFound, route, type Route } from "./http";
import { parsePhrase } from "./phrases";
import {
  between, describeRule, firstMatchingDay, nextAfter, validateRule,
} from "./recurrence";
import { lessonsBetween, weekLabel } from "./schedule";
import { clockOf, dayBounds, dayOf, localDay, momentOf, parseClock, realDay, utc, wall } from "./time";
import { check, dateValue, itemId, queryText, type Fields } from "./validate";

/** LIMITS.reminders: the pending ones. */
const PENDING = 20;
/** LIMITS.reminder_length. */
const TEXT_LENGTH = 200;
/** timeutil.SUPPORTED_YEARS. */
const FIRST_YEAR = 2000;
const LAST_YEAR = 2100;
/** agenda.MAX_DAYS. */
const MAX_DAYS = 62;

const RULE_IN: Fields = {
  repeat: { type: "str", required: true, choices: ["daily", "weekly", "monthly"] },
  time_local: { type: "str", required: true, pattern: /^\d{2}:\d{2}$/ },
  weekdays: { type: "int", nullable: true, ge: 1, le: 127 },
  interval_weeks: { type: "int", choices: [1, 2] },
  month_day: { type: "int", nullable: true, ge: 1, le: 31 },
  anchor_date: { type: "date", nullable: true },
};
const LOCAL_MOMENT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const REMINDER_PATCH: Fields = {
  text: { type: "str", nullable: true, max: 1000 },
  due_local: { type: "str", nullable: true, pattern: LOCAL_MOMENT },
  rule: { type: "model", name: "RuleIn", nullable: true, fields: RULE_IN },
};
const REMINDER_IN: Fields = { ...REMINDER_PATCH, text: { type: "str", required: true, max: 1000 } };
const PARSE_IN: Fields = { text: { type: "str", required: true, max: 1000 } };

interface ReminderInput {
  text?: string | null;
  due_local?: string | null;
  rule?: RuleInput | null;
}

const inYears = (day: string) => Number(day.slice(0, 4)) >= FIRST_YEAR && Number(day.slice(0, 4)) <= LAST_YEAR;

/** The next time of a pending reminder; null for a one-off whose time has come. */
export function nextFiring(visit: Visit, reminder: StoredReminder): number | null {
  if (reminder.rule) return nextAfter(reminder.rule, visit.now(), visit.zone());
  return reminder.due !== null && reminder.due > visit.now() ? reminder.due : null;
}

/** The pending reminders, by their next time. */
export function pending(visit: Visit): { reminder: StoredReminder; due: number }[] {
  return visit.data.reminders
    .flatMap((reminder) => {
      const due = nextFiring(visit, reminder);
      return due === null ? [] : [{ reminder, due }];
    })
    .sort((a, b) => a.due - b.due || a.reminder.id - b.reminder.id);
}

function reminderOut(visit: Visit, reminder: StoredReminder, due: number): Reminder {
  const local = wall(visit.zone(), due);
  return {
    id: reminder.id, text: reminder.text, due_at: utc(due), due_local: `${dayOf(local)}T${clockOf(local)}`,
    status: "pending", repeat: reminder.rule ? reminder.rule.repeat : "none", rule: reminder.rule ? { ...reminder.rule } : null,
    description: reminder.rule ? describeRule(reminder.rule, visit.lang()) : null,
  };
}

/** reminders.clean_text. */
function cleanText(text: string): string {
  const cleaned = text.trim();
  if (codePoints(cleaned) < 1 || codePoints(cleaned) > TEXT_LENGTH) {
    throw invalidInput({ field: "text", reason: "length", limit: TEXT_LENGTH });
  }
  return cleaned;
}

/** The router's _wall: a wall time the calendar has, else due_local's format. */
function wallTime(dueLocal: string): { day: string; time: string } {
  const [day = "", time = ""] = dueLocal.split("T");
  if (!realDay(day) || parseClock(time) !== time) throw invalidInput({ field: "due_local", reason: "format" });
  return { day, time };
}

/** reminders._to_utc: the moment of a wall time, of the years the server keeps. */
function momentFrom(visit: Visit, { day, time }: { day: string; time: string }): number {
  if (!inYears(day)) throw invalidInput({ field: "when", reason: "invalid" });
  return momentOf(visit.zone(), day, time);
}

/** The router's _rule: only the fields the chosen repeat uses, anchored today unless told otherwise. */
function ruleFrom(input: RuleInput, today: string): RepeatRule {
  const anchor = input.anchor_date ?? today;
  if (!inYears(anchor)) throw invalidInput({ field: "rule", reason: "repeat_invalid" });
  const weekly = input.repeat === "weekly";
  return {
    repeat: input.repeat, time_local: input.time_local, anchor_date: anchor,
    weekdays: weekly ? (input.weekdays ?? null) : null,
    interval_weeks: weekly ? (input.interval_weeks ?? 1) : 1,
    month_day: input.repeat === "monthly" ? (input.month_day ?? null) : null,
  };
}

/**
 * A new or changed rule as the series starts: every other week counts from the first matching day
 * (reminders._biweekly_anchor), and the anchor is never before the first real firing.
 */
function started(visit: Visit, rule: RepeatRule): RepeatRule {
  validateRule(rule);
  const now = visit.now();
  const zone = visit.zone();
  let begun = rule;
  if (rule.interval_weeks === 2 && rule.anchor_date >= localDay(zone, now)) {
    const after = `${localDay(zone, now)}T${clockOf(wall(zone, now))}`;
    begun = { ...rule, anchor_date: firstMatchingDay(rule, rule.anchor_date, after) ?? rule.anchor_date };
  }
  const first = localDay(zone, nextAfter(begun, now, zone));
  return { ...begun, anchor_date: begun.anchor_date > first ? begun.anchor_date : first };
}

/** reminders._same_schedule: an edit's rule fires as the stored one; its anchor is noise but for every other week. */
function sameSchedule(next: RepeatRule, current: RepeatRule | null): boolean {
  if (!current) return false;
  if (next.interval_weeks === 2 && next.anchor_date !== current.anchor_date) return false;
  return (["repeat", "time_local", "weekdays", "interval_weeks", "month_day"] as const)
    .every((key) => next[key] === current[key]);
}

function checkLimit(visit: Visit): void {
  if (pending(visit).length >= PENDING) throw limitReached("reminder", PENDING);
}

/** The pending reminder of a path, or 404. */
function reminderOf(visit: Visit, raw: string): { reminder: StoredReminder; due: number } {
  const id = itemId(raw, "reminder_id");
  const found = pending(visit).find((item) => item.reminder.id === id);
  if (!found) throw notFound("reminder");
  return found;
}

function answerWith(visit: Visit, reminder: StoredReminder): Reminder {
  return reminderOut(visit, reminder, nextFiring(visit, reminder) ?? reminder.due ?? visit.now());
}

/** routers/agenda.py: the days from `from` to `to` with their reminders and lessons, by time. */
function agenda(visit: Visit, from: string, to: string): Agenda {
  if (!inYears(from) || !inYears(to)) throw invalidInput({ field: "to", reason: "range" });
  if (to < from || daysBetween(from, to) >= MAX_DAYS) throw invalidInput({ field: "to", reason: "range" });
  const zone = visit.zone();
  const [start] = dayBounds(from, zone);
  const [, end] = dayBounds(to, zone);
  const days = new Map<string, AgendaItem[]>();
  for (let day = from; day <= to; day = addDaysIso(day, 1)) days.set(day, []);
  const firings = pending(visit).flatMap(({ reminder }) => {
    if (!reminder.rule) return reminder.due !== null && start <= reminder.due && reminder.due < end ? [{ reminder, moment: reminder.due }] : [];
    return between(reminder.rule, start, end, zone).map((moment) => ({ reminder, moment }));
  });
  firings.sort((a, b) => a.moment - b.moment || a.reminder.id - b.reminder.id);
  for (const { reminder, moment } of firings) {
    days.get(localDay(zone, moment))?.push({
      kind: "reminder", id: reminder.id, time: clockOf(wall(zone, moment)), text: reminder.text,
      repeat: reminder.rule ? reminder.rule.repeat : "none",
      description: reminder.rule ? describeRule(reminder.rule, visit.lang()) : null,
    });
  }
  for (const lesson of lessonsBetween(visit, start, end)) {
    days.get(localDay(zone, lesson.start))?.push({
      kind: "lesson", time: clockOf(wall(zone, lesson.start)), end: clockOf(wall(zone, lesson.end)),
      title: lesson.title, lesson_kind: lesson.kind, room: lesson.room,
    });
  }
  return {
    days: [...days].map(([date, items]) => ({
      date, label: weekLabel(visit, date), items: items.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0)),
    })),
  };
}

export const REMINDERS: Route[] = [
  route("GET", "/reminders", (visit) =>
    json<Reminder[]>(pending(visit).map(({ reminder, due }) => reminderOut(visit, reminder, due)))),
  route("POST", "/reminders", (visit, { body }) => {
    check(body, REMINDER_IN);
    const input = body as ReminderInput & { text: string };
    if ((input.due_local == null) === (input.rule == null)) throw invalidInput({ field: "due_local", reason: "schedule" });
    let reminder: StoredReminder;
    if (input.rule != null) {
      const rule = ruleFrom(input.rule, visit.today());
      const text = cleanText(input.text);
      validateRule(rule);
      checkLimit(visit);
      reminder = { id: 0, text, due: null, rule: started(visit, rule) };
    } else {
      const when = wallTime(input.due_local ?? "");
      const text = cleanText(input.text);
      const due = momentFrom(visit, when);
      if (due <= visit.now()) throw invalidInput({ field: "when", reason: "past" });
      checkLimit(visit);
      reminder = { id: 0, text, due, rule: null };
    }
    reminder.id = visit.data.next.reminder++;
    visit.data.reminders.push(reminder);
    return created<Reminder>(answerWith(visit, reminder));
  }),
  route("PATCH", "/reminders/{reminder_id}", (visit, { params, body }) => {
    const raw = params.reminder_id ?? "";
    itemId(raw, "reminder_id");
    check(body, REMINDER_PATCH);
    const patch = body as ReminderInput;
    if (patch.due_local != null && patch.rule != null) throw invalidInput({ field: "due_local", reason: "schedule" });
    const when = patch.due_local ? wallTime(patch.due_local) : null;
    const rule = patch.rule ? ruleFrom(patch.rule, visit.today()) : null;
    const { reminder, due: shown } = reminderOf(visit, raw);
    // Every check before any change: a refused edit leaves the reminder as it was.
    const text = patch.text == null ? null : cleanText(patch.text);
    if (rule && sameSchedule(rule, reminder.rule)) {
      // The form sends the whole rule with every edit: a text-only edit keeps the series' firings.
      validateRule(rule);
      if (text !== null) reminder.text = text;
    } else if (rule) {
      const begun = started(visit, rule);
      if (text !== null) reminder.text = text;
      Object.assign(reminder, { rule: begun, due: null });
    } else if (when) {
      const due = momentFrom(visit, when);
      // Its own moment sent back unchanged is no reschedule and no check of the past.
      const unchanged = !reminder.rule && `${when.day}T${when.time}` === reminderOut(visit, reminder, shown).due_local;
      if (!unchanged && due <= visit.now()) throw invalidInput({ field: "when", reason: "past" });
      if (text !== null) reminder.text = text;
      if (!unchanged) Object.assign(reminder, { rule: null, due });
    } else if (text !== null) {
      reminder.text = text;
    }
    return json<Reminder>(answerWith(visit, reminder));
  }),
  route("DELETE", "/reminders/{reminder_id}", (visit, { params }) => {
    const { reminder } = reminderOf(visit, params.reminder_id ?? "");
    visit.data.reminders = visit.data.reminders.filter((item) => item !== reminder);
    return noContent();
  }),
  route("POST", "/reminders/parse", (visit, { body }) => {
    check(body, PARSE_IN);
    return json<ParsedPhrase>(parsePhrase(visit, (body as { text: string }).text));
  }),
  route("GET", "/agenda", (visit, { query }) => {
    const from = dateValue(queryText(query, "from", { required: true }) ?? "", "from");
    const to = dateValue(queryText(query, "to", { required: true }) ?? "", "to");
    return json<Agenda>(agenda(visit, from, to));
  }),
];
