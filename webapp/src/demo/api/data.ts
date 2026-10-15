/**
 * What the demo's API keeps for a visit (spec §5): the records of the visitor, as the server's
 * tables keep a user's, in the host page's memory only. A new visit — a reload, another language,
 * «Начать заново» — starts from the seed again (seeds.ts).
 */
import type {
  AlertMinutes, HabitColor, MoneyEntry, MoneyKind, NoteItem, RepeatRule, ScheduleKind, WeatherCity,
} from "../../api/types";
import type { Lang } from "../../i18n";
import { localDay } from "./time";

/** A place of the weather: the home city, an extra one, a place the search found. */
export interface Place {
  name: string;
  lat: number;
  lon: number;
  timezone: string;
}

/** The user's row: the profile and the settings. */
export interface Profile {
  first_name: string;
  /** The app's language setting; "auto" follows Telegram's, the demo's language. */
  language: "auto" | Lang;
  home: Place;
  morning: { enabled: boolean; time: string };
  can_write: boolean;
  currency: string;
  /** A month's budget of all expenses, in hundredths. */
  budget: number | null;
}

export interface StoredNote {
  id: number;
  text: string;
  created: number;
  /** The text's last change. */
  updated: number;
  /** When it was pinned; null when it is not. */
  pinned: number | null;
  items: NoteItem[];
}

/** A pending reminder: a one-off has its moment, a repeat its rule. */
export interface StoredReminder {
  id: number;
  text: string;
  due: number | null;
  rule: RepeatRule | null;
}

export interface StoredHabit {
  id: number;
  name: string;
  emoji: string;
  color: HabitColor;
  weekly_goal: number;
  created_on: string;
  /** Day → done (true) or missed (false); a day without a mark is not here. */
  marks: Map<string, boolean>;
}

/** The preset categories of money (core/money_style.PRESETS), named by the bot's words. */
export type Preset =
  | "groceries" | "cafe" | "transport" | "home" | "phone" | "health" | "clothes" | "fun" | "study" | "gifts"
  | "subscriptions" | "other" | "salary" | "stipend" | "gifts_in" | "other_in";

export interface StoredCategory {
  id: number;
  kind: MoneyKind;
  /** A preset is named in the user's language until the user renames it. */
  preset: Preset | null;
  name: string | null;
  emoji: string;
  hidden: boolean;
  /** A month's budget, in hundredths: an expense category's only. */
  budget: number | null;
}

/** The connected timetable. */
export interface StoredSource {
  kind: ScheduleKind;
  title: string | null;
  mirea_id: number | null;
  url: string | null;
  fetched: number;
  minutes: AlertMinutes | null;
}

/** A lesson of the sample week: whatever source is connected, the week is this one. */
export interface Lesson {
  /** 0 for Monday. */
  weekday: number;
  start: string;
  end: string;
  title: string;
  kind: string | null;
  room: string | null;
}

export interface Data {
  profile: Profile;
  cities: WeatherCity[];
  notes: StoredNote[];
  reminders: StoredReminder[];
  habits: StoredHabit[];
  categories: StoredCategory[];
  entries: MoneyEntry[];
  /** The budget warnings shown: «2026-10/0/80» — the month, the category (0: all expenses), the threshold. */
  alerts: Set<string>;
  source: StoredSource | null;
  timetable: Lesson[];
  /** The demo's group: the one any search finds. */
  group: { id: number; name: string };
  /** The id the next record of each kind gets. */
  next: { note: number; item: number; city: number; reminder: number; habit: number; entry: number; category: number };
  /** The messages prepared for «Поделиться» so far: each gets an id of its own. */
  shared: number;
}

/** A visit: its data, its clock and its languages. */
export interface Visit {
  readonly data: Data;
  /** The language the demo was opened in: Telegram's language_code, and the data's. */
  readonly language: Lang;
  /** The demo's clock. */
  now(): number;
  /** The user's zone, the home city's: the server counts every day of the user on it. */
  zone(): string;
  /** The user's today. */
  today(): string;
  /** The language of the answers: the app's setting, else Telegram's (views.user_language). */
  lang(): Lang;
}

export function visitOf(data: Data, language: Lang, now: () => number): Visit {
  return {
    data,
    language,
    now,
    zone: () => data.profile.home.timezone,
    today: () => localDay(data.profile.home.timezone, now()),
    lang: () => (data.profile.language === "auto" ? language : data.profile.language),
  };
}
