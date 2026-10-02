export interface City {
  name: string;
  admin?: string | null;
  country?: string | null;
  lat: number;
  lon: number;
  timezone: string;
}

export interface Me {
  id: number;
  first_name: string | null;
  language: "ru" | "en";
  language_setting: "auto" | "ru" | "en";
  city: City;
  morning: { enabled: boolean; time: string };
  can_write: boolean;
}

export interface Weather {
  city: string;
  temperature: number | null;
  feels_like: number | null;
  wind: number | null;
  code: number;
  emoji: string;
  description: string;
  tmin: number | null;
  tmax: number | null;
  tips: string[];
}

export interface Rate {
  value: number;
  change: number;
}

export interface Rates {
  date: string;
  usd: Rate;
  eur: Rate;
}

export type StreakUnit = "days" | "weeks";
export type HabitColor = "mint" | "sky" | "violet" | "rose" | "coral" | "amber" | "sand" | "slate";

export interface Habit {
  id: number;
  name: string;
  emoji: string;
  color: HabitColor;
  /** 1–7 days a week; 7 is a daily habit. */
  weekly_goal: number;
  created_on: string;
  done_today: boolean | null;
  streak: number;
  streak_unit: StreakUnit;
  record: number;
  percent: number;
  week_done: number;
  week_goal: number;
  /** Monday to Sunday: "1" done, "0" missed, "-" no mark, "." before the habit or ahead. */
  week: string;
  done_days: number;
  total_days: number;
  last_days: (boolean | null)[];
}

export interface HabitDetail extends Habit {
  /** A Monday: the first day of `year`. */
  year_from: string;
  /** 371 days (53 weeks) from `year_from`, in the alphabet of `week`. */
  year: string;
}

export interface HabitInput {
  name: string;
  emoji?: string;
  color?: HabitColor;
  weekly_goal?: number;
}

export type HabitPatch = Partial<HabitInput>;

export interface SharedCard {
  prepared_id: string;
}

export interface TodayReminder {
  id: number;
  text: string;
  time: string;
  due_at: string;
}

export interface TodayLesson {
  time: string;
  end: string;
  title: string;
  kind: string | null;
  room: string | null;
  starts_at: string;
  ends_at: string;
}

export interface Today {
  date: string;
  part_of_day: "morning" | "day" | "evening" | "night";
  weather: Weather | null;
  reminders_today: TodayReminder[];
  habits: { done: number; total: number; items: Habit[] };
  notes_count: number;
  rates: Rates | null;
  best_streak: { name: string; count: number; unit: StreakUnit } | null;
  has_schedule: boolean;
  lessons: TodayLesson[];
  week_label: string | null;
}

export interface Note {
  id: number;
  text: string;
  created_at: string;
  updated_at: string;
}

export type RepeatName = "none" | "daily" | "weekly" | "monthly";

export interface RepeatRule {
  repeat: Exclude<RepeatName, "none">;
  time_local: string;
  weekdays: number | null;
  interval_weeks: number;
  month_day: number | null;
  anchor_date: string;
}

export interface RuleInput {
  repeat: Exclude<RepeatName, "none">;
  time_local: string;
  weekdays?: number | null;
  interval_weeks?: 1 | 2;
  month_day?: number | null;
  anchor_date?: string | null;
}

export interface ReminderInput {
  text: string;
  due_local?: string;
  rule?: RuleInput;
}

export interface ReminderItem {
  kind: "reminder";
  id: number;
  time: string;
  text: string;
  repeat: RepeatName;
  description: string | null;
}

export interface LessonItem {
  kind: "lesson";
  time: string;
  end: string;
  title: string;
  lesson_kind: string | null;
  room: string | null;
}

export type AgendaItem = ReminderItem | LessonItem;

export interface AgendaDay {
  date: string;
  /** The timetable's week label for this day, «5 неделя». */
  label: string | null;
  items: AgendaItem[];
}

export interface Agenda {
  days: AgendaDay[];
}

export interface ParsedPhrase {
  text: string;
  repeat: RepeatName;
  date: string | null;
  time: string | null;
  weekdays: number | null;
  interval_weeks: number;
  month_day: number | null;
  description: string | null;
}

export interface Reminder {
  id: number;
  text: string;
  due_at: string;
  due_local: string;
  status: string;
  repeat: RepeatName;
  rule: RepeatRule | null;
  description: string | null;
}

export type ScheduleKind = "mirea" | "url" | "file";

export type AlertMinutes = 5 | 10 | 15 | 30 | 60;

export interface ScheduleSource {
  kind: ScheduleKind;
  title: string | null;
  mirea_id: number | null;
  url: string | null;
  fetched_at: string;
  ok_at: string | null;
  error: string | null;
  stale: boolean;
  lesson_reminder_minutes: AlertMinutes | null;
  lessons_ahead: number;
}

export interface ScheduleState {
  source: ScheduleSource | null;
}

export interface Group {
  id: number;
  name: string;
}

export interface GroupSearch {
  groups: Group[];
  /** No full crawl of the MIREA directory has finished yet: a group may be missing for now. */
  building: boolean;
}

export interface Health {
  status: "ok";
  version: string;
  commit: string | null;
}
