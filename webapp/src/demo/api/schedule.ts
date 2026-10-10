/**
 * The timetable (routers/schedule.py, services/schedule.py and services/groups.py): its source,
 * the search of MIREA's groups, connecting, refreshing, the reminder before a lesson. In the demo
 * any search finds the demo's group (spec §5.1), and whatever is connected — the group, a link, a
 * file — the lessons are the sample week's, on MIREA's clock, with the week numbers of the term.
 */
import type { GroupSearch, ScheduleSource, ScheduleState } from "../../api/types";
import { addDaysIso, codePoints, daysBetween, mondayOf } from "../../lib/format";
import type { FileBody } from "../bridge/contract";
import type { StoredSource, Visit } from "./data";
import { invalidInput, json, noContent, notFound, route, type Route } from "./http";
import { DAY, dayBounds, localDay, momentOf, utc, weekdayOf } from "./time";
import { check, queryText, type Fields } from "./validate";
import { SEED_WORDS } from "./words";

/** group_names.MIREA_ZONE: the timetable's clock. */
const MIREA_ZONE = "Europe/Moscow";
/** schedule.FILE_LIMIT. */
const FILE_LIMIT = 2 * 1024 * 1024;
/** schedule.TITLE_LENGTH. */
const TITLE_LENGTH = 100;
/** schedule.STALE_AFTER: a timetable not fetched for this long is shown as old. */
const STALE_AFTER = 3 * DAY;
/** The weeks of a term; out of term the numbers go round again. */
const TERM_WEEKS = 17;

const SCHEDULE_IN: Fields = {
  mirea_id: { type: "int", nullable: true, ge: 1, le: 1_000_000 },
  url: { type: "str", nullable: true, max: 2000 },
};
const SCHEDULE_PATCH: Fields = {
  lesson_reminder_minutes: { type: "int", required: true, nullable: true, choices: [5, 10, 15, 30, 60] },
};

/** A lesson at its moments. */
export interface LessonAt {
  title: string;
  kind: string | null;
  room: string | null;
  start: number;
  end: number;
}

/** The first Monday of the term a day is in: autumn's from the week of 1 September, spring's from the week of 9 February. */
function termStart(day: string): string {
  const year = Number(day.slice(0, 4));
  const autumn = mondayOf(`${year}-09-01`);
  const spring = mondayOf(`${year}-02-09`);
  return day >= autumn ? autumn : day >= spring ? spring : mondayOf(`${year - 1}-09-01`);
}

/** The week of the term, from 1; past the term's last week the numbers go round. */
function termWeek(day: string): number {
  return (Math.floor(daysBetween(termStart(day), day) / 7) % TERM_WEEKS) + 1;
}

/** The timetable's label of a day — «6 неделя» — or null without a timetable. */
export function weekLabel(visit: Visit, day: string): string | null {
  return visit.data.source ? SEED_WORDS[visit.language].week(termWeek(day)) : null;
}

/** The lessons that begin in [start, end), the first first; none without a timetable. */
export function lessonsBetween(visit: Visit, start: number, end: number): LessonAt[] {
  if (!visit.data.source) return [];
  const found: LessonAt[] = [];
  const last = localDay(MIREA_ZONE, end);
  for (let day = addDaysIso(localDay(MIREA_ZONE, start), -1); day <= last; day = addDaysIso(day, 1)) {
    const weekday = weekdayOf(day);
    for (const lesson of visit.data.timetable) {
      if (lesson.weekday !== weekday) continue;
      const at = momentOf(MIREA_ZONE, day, lesson.start);
      if (start <= at && at < end) {
        found.push({ title: lesson.title, kind: lesson.kind, room: lesson.room, start: at, end: momentOf(MIREA_ZONE, day, lesson.end) });
      }
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

/** The lessons of a day of the user's. */
export function lessonsOn(visit: Visit, day: string): LessonAt[] {
  return lessonsBetween(visit, ...dayBounds(day, visit.zone()));
}

function sourceOut(visit: Visit, source: StoredSource): ScheduleSource {
  const now = visit.now();
  // The lessons still ahead in the term's weeks.
  const today = localDay(MIREA_ZONE, now);
  const termEnd = addDaysIso(mondayOf(today), 7 * (TERM_WEEKS - termWeek(today) + 1));
  return {
    kind: source.kind, title: source.title, mirea_id: source.mirea_id, url: source.url,
    fetched_at: utc(source.fetched), ok_at: utc(source.fetched), error: null, stale: now - source.fetched > STALE_AFTER,
    lesson_reminder_minutes: source.minutes,
    lessons_ahead: lessonsBetween(visit, now + 1, momentOf(MIREA_ZONE, termEnd)).length,
  };
}

function state(visit: Visit): ScheduleState {
  const { source } = visit.data;
  return { source: source ? sourceOut(visit, source) : null };
}

/** calendars.normalize: an https link to a host (webcal:// stands for one), else forbidden_host. */
function calendarLink(raw: string): { url: string; host: string } {
  const forbidden = () => invalidInput({ field: "url", reason: "forbidden_host" });
  let text = raw.trim();
  if (codePoints(text) > 2000) throw forbidden();
  if (text.toLowerCase().startsWith("webcal://")) text = `https://${text.slice("webcal://".length)}`;
  let link: URL;
  try {
    link = new URL(text);
  } catch {
    throw forbidden();
  }
  if (link.protocol !== "https:" || !link.hostname || link.username || link.password || link.port !== "") throw forbidden();
  return { url: text, host: link.hostname };
}

/** The source connected now, its title cut in code points: the reminder before a lesson stays as it was. */
function connect(visit: Visit, source: Omit<StoredSource, "fetched" | "minutes">): ScheduleState {
  const title = Array.from((source.title ?? "").trim()).slice(0, TITLE_LENGTH).join("");
  visit.data.source = { ...source, title: title || null, fetched: visit.now(), minutes: visit.data.source?.minutes ?? null };
  return state(visit);
}

function sourceOf(visit: Visit): StoredSource {
  if (!visit.data.source) throw notFound("schedule");
  return visit.data.source;
}

function isFile(body: unknown): body is FileBody {
  return typeof body === "object" && body !== null && "size" in body;
}

export const SCHEDULE: Route[] = [
  route("GET", "/schedule", (visit) => json<ScheduleState>(state(visit))),
  route("GET", "/schedule/groups", (visit, { query }) => {
    const q = queryText(query, "q", { max: 40 }) ?? "";
    const groups = codePoints(q.trim()) >= 2 ? [{ ...visit.data.group }] : [];
    return json<GroupSearch>({ groups, building: false });
  }),
  route("PUT", "/schedule", (visit, { body }) => {
    check(body, SCHEDULE_IN);
    const input = body as { mirea_id?: number | null; url?: string | null };
    if ((input.mirea_id == null) === (input.url == null)) throw invalidInput({ field: "schedule", reason: "source" });
    if (input.mirea_id != null) {
      if (input.mirea_id !== visit.data.group.id) throw notFound("group");
      // MIREA's own address of the calendar stays out of the demo: the app never shows it.
      return json<ScheduleState>(connect(visit, { kind: "mirea", title: visit.data.group.name, mirea_id: input.mirea_id, url: null }));
    }
    const link = calendarLink(input.url ?? "");
    return json<ScheduleState>(connect(visit, { kind: "url", title: link.host, mirea_id: null, url: link.url }));
  }),
  route("POST", "/schedule/file", (visit, { query, body }) => {
    const name = queryText(query, "name", { max: 255 });
    if (isFile(body) && body.size > FILE_LIMIT) throw invalidInput({ field: "file", reason: "too_large" });
    let stem = (name ?? "").replaceAll("\\", "/").split("/").at(-1) ?? "";
    if (stem.toLowerCase().endsWith(".ics")) stem = stem.slice(0, -".ics".length);
    return json<ScheduleState>(connect(visit, { kind: "file", title: stem, mirea_id: null, url: null }));
  }),
  route("POST", "/schedule/refresh", (visit) => {
    sourceOf(visit).fetched = visit.now();
    return json<ScheduleState>(state(visit));
  }),
  route("PATCH", "/schedule", (visit, { body }) => {
    check(body, SCHEDULE_PATCH);
    sourceOf(visit).minutes = (body as { lesson_reminder_minutes: ScheduleSource["lesson_reminder_minutes"] }).lesson_reminder_minutes;
    return json<ScheduleState>(state(visit));
  }),
  route("DELETE", "/schedule", (visit) => {
    sourceOf(visit);
    visit.data.source = null;
    return noContent();
  }),
];
