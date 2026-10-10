/**
 * The habits (routers/habits.py, services/habits.py): each with its statistics on the user's
 * today — the streak, the record, the percent of the last year, the week — and one with its year
 * of marks; created, changed, marked, and its card shared or sent. Nothing is drawn: the host
 * page's chat picker shows the README's sample card.
 */
import type { Habit, HabitColor, HabitDetail, SharedCard } from "../../api/types";
import { addDaysIso, codePoints, daysBetween, mondayOf } from "../../lib/format";
import { COLORS, DAILY, EMOJI } from "../../lib/habits";
import type { StoredHabit, Visit } from "./data";
import {
  created, invalidInput, json, limitReached, noContent, notFound, route, writeForbidden, type Route,
} from "./http";
import { preparedId } from "./prepared";
import { check, dateValue, itemId, type Fields } from "./validate";

/** LIMITS.habits and LIMITS.habit_length. */
const HABITS_LIMIT = 10;
const NAME_LENGTH = 50;
/** habits.LAST_DAYS, YEAR_DAYS and YEAR_WEEKS. */
const LAST_DAYS = 9;
const YEAR_DAYS = 365;
const YEAR_WEEKS = 53;

const LOOK: Fields = {
  emoji: { type: "str", nullable: true, max: 16 },
  color: { type: "str", nullable: true, max: 16 },
  weekly_goal: { type: "int", nullable: true, ge: 1, le: 7 },
};
const HABIT_IN: Fields = { name: { type: "str", required: true, max: 1000 }, ...LOOK };
const HABIT_PATCH: Fields = { name: { type: "str", nullable: true, max: 1000 }, ...LOOK };
const MARK_IN: Fields = { done: { type: "bool", required: true, nullable: true } };

interface HabitInput {
  name?: string | null;
  emoji?: string | null;
  color?: string | null;
  weekly_goal?: number | null;
}

type Marks = ReadonlyMap<string, boolean>;

/** The goal of the week from `weekStart`: a week that `first` cuts asks only for the days it has left. */
const weekGoal = (goal: number, weekStart: string, first: string) =>
  Math.min(goal, 7 - Math.max(daysBetween(weekStart, first), 0));

function doneInWeek(marks: Marks, weekStart: string, first: string): number {
  return Array.from({ length: 7 }, (_, offset) => addDaysIso(weekStart, offset))
    .filter((day) => day >= first && marks.get(day) === true).length;
}

const weekMet = (marks: Marks, weekStart: string, goal: number, first: string) =>
  doneInWeek(marks, weekStart, first) >= weekGoal(goal, weekStart, first);

/** part / whole in whole percent, halves up: 100 only when nothing is missing, 0 only when nothing is done. */
function share(part: number, whole: number): number {
  if (!whole) return 0;
  let rounded = Math.floor((200 * part + whole) / (2 * whole));
  if (part < whole) rounded = Math.min(rounded, 99);
  if (part > 0) rounded = Math.max(rounded, 1);
  return rounded;
}

function dailyStreak(marks: Marks, today: string): number {
  let streak = 0;
  for (let day = marks.has(today) ? today : addDaysIso(today, -1); marks.get(day) === true; day = addDaysIso(day, -1)) {
    streak += 1;
  }
  return streak;
}

/** Weeks in a row whose goal was met, up to this week if it is met already: a week still going breaks nothing. */
function weeklyStreak(marks: Marks, goal: number, created: string, today: string): number {
  let week = mondayOf(today);
  if (!weekMet(marks, week, goal, created)) week = addDaysIso(week, -7);
  let streak = 0;
  for (; week >= mondayOf(created) && weekMet(marks, week, goal, created); week = addDaysIso(week, -7)) streak += 1;
  return streak;
}

function dailyRecord(marks: Marks): number {
  let best = 0;
  let run = 0;
  let previous: string | null = null;
  for (const day of [...marks].filter(([, done]) => done).map(([day]) => day).sort()) {
    run = previous !== null && daysBetween(previous, day) === 1 ? run + 1 : 1;
    best = Math.max(best, run);
    previous = day;
  }
  return best;
}

function weeklyRecord(marks: Marks, goal: number, created: string, today: string): number {
  let best = 0;
  let run = 0;
  for (let week = mondayOf(created); week <= mondayOf(today); week = addDaysIso(week, 7)) {
    if (weekMet(marks, week, goal, created)) best = Math.max(best, (run += 1));
    else if (week < mondayOf(today)) run = 0;
  }
  return best;
}

/** Done days (a daily habit) or met weeks (a weekly one) of the last year, never before the habit began. */
function yearPercent(marks: Marks, goal: number, created: string, today: string): number {
  const back = addDaysIso(today, -(YEAR_DAYS - 1));
  const first = created > back ? created : back;
  if (goal === DAILY) {
    const last = marks.has(today) ? today : addDaysIso(today, -1);
    const done = [...marks].filter(([day, mark]) => mark && first <= day && day <= last).length;
    return share(done, Math.max(daysBetween(first, last) + 1, 0));
  }
  let met = 0;
  let counted = 0;
  for (let week = mondayOf(first); week <= mondayOf(today); week = addDaysIso(week, 7)) {
    const ok = weekMet(marks, week, goal, first);
    if (ok || week < mondayOf(today)) {
      counted += 1;
      met += ok ? 1 : 0;
    }
  }
  return share(met, counted);
}

/** A day of the habit: «1» done, «0» missed, «-» no mark, «.» before the habit or ahead. */
function cell(marks: Marks, day: string, created: string, today: string): string {
  if (day < created || day > today) return ".";
  const mark = marks.get(day);
  return mark === undefined ? "-" : mark ? "1" : "0";
}

export function habitOut(habit: StoredHabit, today: string): Habit {
  const { marks, weekly_goal: goal, created_on: created } = habit;
  const thisWeek = mondayOf(today);
  const daily = goal === DAILY;
  const streak = daily ? dailyStreak(marks, today) : weeklyStreak(marks, goal, created, today);
  const record = daily ? dailyRecord(marks) : weeklyRecord(marks, goal, created, today);
  return {
    id: habit.id, name: habit.name, emoji: habit.emoji, color: habit.color, weekly_goal: goal, created_on: created,
    day: today, done_today: marks.get(today) ?? null, streak, streak_unit: daily ? "days" : "weeks",
    record: Math.max(record, streak), percent: yearPercent(marks, goal, created, today),
    week_done: doneInWeek(marks, thisWeek, created), week_goal: weekGoal(goal, thisWeek, created),
    week: Array.from({ length: 7 }, (_, offset) => cell(marks, addDaysIso(thisWeek, offset), created, today)).join(""),
    done_days: [...marks.values()].filter(Boolean).length,
    total_days: Math.max(daysBetween(created, today) + 1, 1),
    last_days: Array.from({ length: LAST_DAYS }, (_, index) => marks.get(addDaysIso(today, index - (LAST_DAYS - 1))) ?? null),
  };
}

function detailOut(habit: StoredHabit, today: string): HabitDetail {
  const start = addDaysIso(mondayOf(today), -7 * (YEAR_WEEKS - 1));
  const year = Array.from({ length: YEAR_WEEKS * 7 }, (_, offset) =>
    cell(habit.marks, addDaysIso(start, offset), habit.created_on, today)).join("");
  return { ...habitOut(habit, today), year_from: start, year };
}

/** habits.pick_best: the longest current streak, a week weighed as seven days, in its own unit. */
export function bestStreak(items: readonly Habit[]): { name: string; count: number; unit: Habit["streak_unit"] } | null {
  const worth = (item: Habit) => item.streak * (item.streak_unit === "days" ? 1 : 7);
  let best: Habit | null = null;
  for (const item of items) if (item.streak > 0 && (best === null || worth(item) > worth(best))) best = item;
  return best && { name: best.name, count: best.streak, unit: best.streak_unit };
}

/** The user's habit of a path, or 404. */
function habitOf(visit: Visit, raw: string): StoredHabit {
  const id = itemId(raw, "habit_id");
  const habit = visit.data.habits.find((item) => item.id === id);
  if (!habit) throw notFound("habit");
  return habit;
}

function cleanName(name: string): string {
  const cleaned = name.trim();
  if (codePoints(cleaned) < 1 || codePoints(cleaned) > NAME_LENGTH) {
    throw invalidInput({ field: "name", reason: "length", limit: NAME_LENGTH });
  }
  return cleaned;
}

/** habits._check_look: an emoji of the set, a colour of the palette, a goal of one to seven days. */
function checkLook(emoji: string, color: string, goal: number): void {
  if (!(EMOJI as readonly string[]).includes(emoji)) throw invalidInput({ field: "emoji", reason: "invalid" });
  if (!(COLORS as readonly string[]).includes(color)) throw invalidInput({ field: "color", reason: "invalid" });
  if (goal < 1 || goal > DAILY) throw invalidInput({ field: "weekly_goal", reason: "out_of_range" });
}

const sameName = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

export const HABITS: Route[] = [
  route("GET", "/habits", (visit) => json<Habit[]>(visit.data.habits.map((habit) => habitOut(habit, visit.today())))),
  route("GET", "/habits/{habit_id}", (visit, { params }) =>
    json<HabitDetail>(detailOut(habitOf(visit, params.habit_id ?? ""), visit.today()))),
  route("POST", "/habits", (visit, { body }) => {
    check(body, HABIT_IN);
    const input = body as HabitInput & { name: string };
    const name = cleanName(input.name);
    const look = { emoji: input.emoji ?? "🎯", color: (input.color ?? "mint") as HabitColor, weekly_goal: input.weekly_goal ?? DAILY };
    checkLook(look.emoji, look.color, look.weekly_goal);
    if (visit.data.habits.some((habit) => sameName(habit.name, name))) throw invalidInput({ field: "name", reason: "duplicate" });
    if (visit.data.habits.length >= HABITS_LIMIT) throw limitReached("habit", HABITS_LIMIT);
    const habit: StoredHabit = { id: visit.data.next.habit++, name, ...look, created_on: visit.today(), marks: new Map() };
    visit.data.habits.push(habit);
    return created<Habit>(habitOut(habit, visit.today()));
  }),
  route("PATCH", "/habits/{habit_id}", (visit, { params, body }) => {
    const raw = params.habit_id ?? "";
    itemId(raw, "habit_id");
    check(body, HABIT_PATCH);
    const patch = body as HabitInput;
    const habit = habitOf(visit, raw);
    checkLook(patch.emoji ?? habit.emoji, patch.color ?? habit.color, patch.weekly_goal ?? habit.weekly_goal);
    const name = patch.name == null ? null : cleanName(patch.name);
    if (name !== null && visit.data.habits.some((other) => other !== habit && sameName(other.name, name))) {
      throw invalidInput({ field: "name", reason: "duplicate" });
    }
    // A new goal recounts the whole history: the goals a habit had before are not kept.
    Object.assign(habit, {
      name: name ?? habit.name, emoji: patch.emoji ?? habit.emoji, color: patch.color ?? habit.color,
      weekly_goal: patch.weekly_goal ?? habit.weekly_goal,
    });
    return json<Habit>(habitOut(habit, visit.today()));
  }),
  route("DELETE", "/habits/{habit_id}", (visit, { params }) => {
    const habit = habitOf(visit, params.habit_id ?? "");
    visit.data.habits = visit.data.habits.filter((item) => item !== habit);
    return noContent();
  }),
  route("PUT", "/habits/{habit_id}/marks/{day}", (visit, { params, body }) => {
    const raw = params.habit_id ?? "";
    itemId(raw, "habit_id");
    const day = dateValue(params.day ?? "", "day");
    check(body, MARK_IN);
    const habit = habitOf(visit, raw);
    const today = visit.today();
    if (day < habit.created_on || day > today) throw invalidInput({ field: "day", reason: "out_of_range" });
    const done = (body as { done: boolean | null }).done;
    if (done === null) habit.marks.delete(day);
    else habit.marks.set(day, done);
    return json<Habit>(habitOut(habit, today));
  }),
  route("POST", "/habits/{habit_id}/share", (visit, { params }) => {
    const habit = habitOf(visit, params.habit_id ?? "");
    visit.data.shared += 1;
    return json<SharedCard>({ prepared_id: preparedId("habit", habit.id, visit.data.shared) });
  }),
  route("POST", "/habits/{habit_id}/card", (visit, { params }) => {
    habitOf(visit, params.habit_id ?? "");
    if (!visit.data.profile.can_write) throw writeForbidden();
    return noContent();
  }),
];
