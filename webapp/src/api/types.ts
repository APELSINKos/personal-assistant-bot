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
  /** ISO 4217: the currency the user keeps accounts in. */
  currency: string;
  /** A month's, in hundredths; null without a budget. */
  money_budget: number | null;
}

/** What `PATCH /me` changes; every field may be left out. */
export interface MePatch {
  language?: "auto" | "ru" | "en";
  morning_enabled?: boolean;
  morning_time?: string;
  currency?: string;
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
  money: TodayMoney | null;
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

export type MoneyKind = "expense" | "income";

export interface MoneyCategory {
  id: number;
  kind: MoneyKind;
  /** In the user's language. */
  name: string;
  emoji: string;
  hidden: boolean;
  /** False for the «Другое» of each kind: whatever the bot cannot place goes there. */
  can_hide: boolean;
  /** A month's, in hundredths; an expense category's only. */
  budget: number | null;
}

/** Every amount of the money API is in hundredths: 250 ₽ is 25000. */
export interface MoneyEntry {
  id: number;
  amount: number;
  category_id: number;
  note: string;
  day: string;
}

export interface CategoryTotal {
  category_id: number;
  amount: number;
  /** Percent of the month's expenses; 0 for an income. */
  share: number;
  /** What the category's budget leaves; below zero when it is overspent. */
  left: number | null;
}

export interface MoneyMonth {
  /** «2026-10». */
  month: string;
  /** The month of the oldest entry; null without entries. */
  first_month: string | null;
  currency: string;
  spent: number;
  income: number;
  balance: number;
  budget: number | null;
  left: number | null;
  /** What the budget leaves for each day to the month's end, today included. */
  per_day: number | null;
  /** The largest first. */
  expenses: CategoryTotal[];
  incomes: CategoryTotal[];
  /** Spent on each day of the month; null for the days ahead. */
  days: (number | null)[];
  /** All of them, the hidden ones too. */
  categories: MoneyCategory[];
  /** The newest first. */
  entries: MoneyEntry[];
}

/** An entry as the form sends it; the amount is a decimal with a point («430.50»). */
export interface MoneyEntryInput {
  amount: string;
  category_id: number;
  note: string;
  day: string;
}

export interface MoneyAlert {
  /** null: the budget of all expenses. */
  category_id: number | null;
  emoji: string | null;
  name: string | null;
  threshold: 80 | 100;
  spent: number;
  budget: number;
}

export interface MoneyEntrySaved {
  entry: MoneyEntry;
  /** The budget warnings this change set off. */
  alerts: MoneyAlert[];
}

export interface MoneyCategoryInput {
  kind: MoneyKind;
  name: string;
  emoji: string;
}

export interface MoneyCategoryPatch {
  name?: string;
  emoji?: string;
  hidden?: boolean;
  /** A decimal with a point; null removes the budget. */
  budget?: string | null;
}

export interface TodayMoney {
  currency: string;
  /** Spent today. */
  today: number;
  /** Spent this month. */
  spent: number;
  budget: number | null;
  left: number | null;
  per_day: number | null;
  /** This month's entries. */
  count: number;
}

export interface CurrencyRate {
  code: string;
  /** In the user's language. */
  name: string;
  /** Roubles for one unit. */
  value: number;
  change: number;
}

export interface RatesAll {
  date: string;
  /** USD, EUR and the user's currency first, the others by name. */
  currencies: CurrencyRate[];
}

export interface RatePoint {
  day: string;
  value: number;
}

export interface RateHistory {
  code: string;
  /** The oldest first; working days only. */
  points: RatePoint[];
}
