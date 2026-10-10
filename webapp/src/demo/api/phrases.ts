/**
 * A phrase of a reminder (routers/reminders.py's parse, services/phrases.py): a few of the bot's
 * rules — the day (сегодня, завтра, послезавтра; today, tomorrow), the time («в 9:30», «19.45»,
 * «at 9:30») and the repeat (каждый день, по будням; every day, on weekdays). What is left of the
 * words is the reminder's text. Words are matched one by one: no pattern looks behind.
 */
import type { ParsedPhrase, RepeatName, RepeatRule } from "../../api/types";
import { addDaysIso, codePoints } from "../../lib/format";
import type { Visit } from "./data";
import { invalidInput } from "./http";
import { describeRule, nextAfter, WEEKDAYS } from "./recurrence";
import { localDay, momentOf } from "./time";

/** LIMITS.reminder_length. */
const TEXT_LENGTH = 200;

/** What a phrase says. */
interface Parsed {
  text: string;
  time: string | null;
  /** Days from today: 0 today, 1 tomorrow. */
  days: number | null;
  repeat: RepeatName;
  weekdays: number | null;
}

/** The words of a day, of a repeat — each a run of words — and what they mean. */
const DAYS: readonly [readonly string[], number][] = [
  [["послезавтра"], 2], [["day", "after", "tomorrow"], 2], [["завтра"], 1], [["tomorrow"], 1],
  [["сегодня"], 0], [["today"], 0],
];
const REPEATS: readonly [readonly string[], RepeatName, number | null][] = [
  [["каждый", "день"], "daily", null], [["ежедневно"], "daily", null], [["every", "day"], "daily", null],
  [["daily"], "daily", null], [["по", "будням"], "weekly", WEEKDAYS], [["on", "weekdays"], "weekly", WEEKDAYS],
];
/** «9:30», «19.45». */
const CLOCK = /^([01]?\d|2[0-3])[:.]([0-5]\d)$/;

/** The phrase's words with the ones it understood taken out; null when it understood none. */
function parse(phrase: string): Parsed | null {
  const words = phrase.split(/\s+/).filter(Boolean);
  const lower = words.map((word) => word.toLowerCase());
  const taken = new Set<number>();
  /** Takes the first run of `run` among the words still there; whether it was there. */
  const take = (run: readonly string[]) => {
    for (let start = 0; start + run.length <= lower.length; start += 1) {
      const at = Array.from(run, (_, offset) => start + offset);
      if (at.every((index, offset) => !taken.has(index) && lower[index] === run[offset])) {
        for (const index of at) taken.add(index);
        return true;
      }
    }
    return false;
  };
  const parsed: Parsed = { text: "", time: null, days: null, repeat: "none", weekdays: null };
  const clock = lower.findIndex((word) => CLOCK.test(word));
  if (clock >= 0) {
    const [, hours = "0", minutes = "00"] = CLOCK.exec(lower[clock] ?? "") ?? [];
    parsed.time = `${hours.padStart(2, "0")}:${minutes}`;
    taken.add(clock);
    if (clock > 0 && ["в", "at"].includes(lower[clock - 1] ?? "")) taken.add(clock - 1);
  }
  const day = DAYS.find(([run]) => take(run));
  if (day) parsed.days = day[1];
  const repeat = REPEATS.find(([run]) => take(run));
  if (repeat) [, parsed.repeat, parsed.weekdays] = repeat;
  if (parsed.time === null && parsed.days === null && parsed.repeat === "none") return null;
  parsed.text = words.filter((_, index) => !taken.has(index)).join(" ");
  return parsed;
}

/** POST /reminders/parse: what the form fills in from a phrase. */
export function parsePhrase(visit: Visit, phrase: string): ParsedPhrase {
  const parsed = parse(phrase);
  if (!parsed) throw invalidInput({ field: "text", reason: "phrase_not_understood" });
  const text = parsed.text.trim();
  // No text left is fine: the form keeps its own text field. Only too long is refused.
  if (codePoints(text) > TEXT_LENGTH) throw invalidInput({ field: "text", reason: "length", limit: TEXT_LENGTH });
  const now = visit.now();
  const zone = visit.zone();
  const today = localDay(zone, now);
  let date: string | null = null;
  let rule: RepeatRule | null = null;
  if (parsed.repeat !== "none") {
    if (parsed.time !== null) {
      rule = {
        repeat: parsed.repeat, time_local: parsed.time, weekdays: parsed.weekdays, interval_weeks: 1, month_day: null,
        anchor_date: today,
      };
      date = localDay(zone, nextAfter(rule, now, zone));
    }
  } else if (parsed.days !== null) {
    date = addDaysIso(today, parsed.days);
  } else if (parsed.time !== null) {
    // A time alone is today's, or tomorrow's once today's has passed.
    date = momentOf(zone, today, parsed.time) > now ? today : addDaysIso(today, 1);
  }
  return {
    text, repeat: parsed.repeat, date, time: parsed.time, weekdays: parsed.weekdays, interval_weeks: 1, month_day: null,
    description: rule && describeRule(rule, visit.lang()),
  };
}
