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

export interface Habit {
  id: number;
  name: string;
  created_on: string;
  done_today: boolean | null;
  streak: number;
  done_days: number;
  total_days: number;
  last_days: (boolean | null)[];
}

export interface TodayReminder {
  id: number;
  text: string;
  time: string;
  due_at: string;
}

export interface Today {
  date: string;
  part_of_day: "morning" | "day" | "evening" | "night";
  weather: Weather | null;
  reminders_today: TodayReminder[];
  habits: { done: number; total: number; items: Habit[] };
  notes_count: number;
  rates: Rates | null;
  best_streak: { name: string; days: number } | null;
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

export interface AgendaItem {
  kind: "reminder";
  id: number;
  time: string;
  text: string;
  repeat: RepeatName;
  description: string | null;
}

export interface AgendaDay {
  date: string;
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

export interface Health {
  status: "ok";
  version: string;
  commit: string | null;
}
