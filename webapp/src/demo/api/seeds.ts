/**
 * The demo's data at the start of a visit (spec §5.2, §5.3): the made-up user «Саша» / «Alex» in
 * Moscow, in the language the demo was opened in. What a day holds — the marks of the habits, the
 * money spent — comes from a hash of the date, so a past day stays as it was from one visit to the
 * next and the same minute gives the same data; reminders are laid out from that minute.
 */
import type { MoneyEntry, NoteItem, WeatherCity } from "../../api/types";
import type { Lang } from "../../i18n";
import { addDaysIso } from "../../lib/format";
import { DAILY } from "../../lib/habits";
import type { Data, Lesson, Preset, StoredCategory, StoredHabit, StoredNote, StoredReminder } from "./data";
import { knownPlace, placeOut } from "./places";
import { chance, draws } from "./random";
import { WEEKDAYS } from "./recurrence";
import { HOUR, localDay, momentOf, monthStart, MINUTE, weekdayOf } from "./time";
import { SEED_WORDS, WORDS, type SeedWords } from "./words";

/** Where the visitor lives: Moscow, on Moscow's clock. */
const HOME = knownPlace(524901);
const ZONE = HOME.timezone;
/** The extra cities of the weather: Тула, Петропавловск-Камчатский (UTC+12), Ереван. */
const EXTRA = [480562, 2122104, 616052];

/** core/money_style.PRESETS, in their order, with their emoji. */
const PRESETS: readonly [Preset, "expense" | "income", string][] = [
  ["groceries", "expense", "🛒"], ["cafe", "expense", "☕"], ["transport", "expense", "🚌"],
  ["home", "expense", "🏠"], ["phone", "expense", "📱"], ["health", "expense", "💊"],
  ["clothes", "expense", "👕"], ["fun", "expense", "🎮"], ["study", "expense", "📚"],
  ["gifts", "expense", "🎁"], ["subscriptions", "expense", "📺"], ["other", "expense", "📦"],
  ["salary", "income", "💼"], ["stipend", "income", "🎓"], ["gifts_in", "income", "🎀"], ["other_in", "income", "💰"],
];
/** The budgets of the month: all expenses and two categories, in hundredths. */
const BUDGET = 3_000_000;
const CATEGORY_BUDGETS: Partial<Record<Preset, number>> = { cafe: 400_000, fun: 300_000 };

/** The demo's group in MIREA's directory: any search finds it. */
const GROUP_ID = 4242;

function notes(words: SeedWords["notes"], now: number, item: () => number): StoredNote[] {
  const note = (id: number, text: string, hoursAgo: number, pinnedAgo: number | null, items: NoteItem[] = []) => ({
    id, text, created: now - hoursAgo * HOUR, updated: now - hoursAgo * HOUR,
    pinned: pinnedAgo === null ? null : now - pinnedAgo * HOUR, items,
  });
  const packing = words.packingItems.map((text, index) => ({ id: item(), text, done: index < 4 }));
  return [
    note(1, words.pancakes, 120, null),
    note(2, words.coursework, 75, null),
    note(3, words.door, 50, 26),
    note(4, words.packing, 30, 5, packing),
  ];
}

function reminders(words: SeedWords["reminders"], now: number): StoredReminder[] {
  const today = localDay(ZONE, now);
  // The parcel: at the first :00 or :30 at least an hour and a half ahead, while it is still today.
  const soon = Math.ceil((now + 90 * MINUTE) / (30 * MINUTE)) * 30 * MINUTE;
  const anchor = addDaysIso(today, -30);
  const list: StoredReminder[] = [
    { id: 2, text: words.lab, due: momentOf(ZONE, addDaysIso(today, 1), "10:00"), rule: null },
    {
      id: 3, text: words.water, due: null,
      rule: { repeat: "daily", time_local: "08:00", weekdays: null, interval_weeks: 1, month_day: null, anchor_date: anchor },
    },
    {
      id: 4, text: words.workout, due: null,
      rule: { repeat: "weekly", time_local: "07:30", weekdays: WEEKDAYS, interval_weeks: 1, month_day: null, anchor_date: anchor },
    },
  ];
  if (localDay(ZONE, soon) === today) list.unshift({ id: 1, text: words.parcel, due: soon, rule: null });
  return list;
}

/**
 * A habit's marks from the day it began to yesterday, each day's by its hash: done at `rate`, and
 * otherwise missed or left unmarked. A weekly habit is marked on Mondays, Wednesdays and Fridays.
 * Today is open: the visitor marks it.
 */
function habit(
  id: number, key: string, name: string, look: Pick<StoredHabit, "emoji" | "color" | "weekly_goal">,
  age: number, rate: number, today: string, language: Lang,
): StoredHabit {
  const marks = new Map<string, boolean>();
  for (let back = age; back >= 1; back -= 1) {
    const day = addDaysIso(today, -back);
    if (look.weekly_goal !== DAILY && ![0, 2, 4].includes(weekdayOf(day))) continue;
    const draw = draws(day, language, "habit", key);
    if (draw() < rate) marks.set(day, true);
    else if (draw() < 0.6) marks.set(day, false);
  }
  return { id, name, ...look, created_on: addDaysIso(today, -age), marks };
}

/** The day of a month the clothes were bought on. */
function clothesDay(month: string, language: Lang): number {
  return 1 + Math.floor(chance(month, language, "clothes") * 27);
}

/**
 * The money of the visitor from the first day of the month before last up to today: the day's
 * draws decide what was bought and for how much; today has only what a morning has.
 */
function spending(language: Lang, today: string, categoryOf: (preset: Preset) => number): Omit<MoneyEntry, "id">[] {
  const words = SEED_WORDS[language].money;
  const found: Omit<MoneyEntry, "id">[] = [];
  const first = monthStart(addDaysIso(monthStart(addDaysIso(monthStart(today), -1)), -1));
  for (let day = first; day <= today; day = addDaysIso(day, 1)) {
    const draw = draws(day, language, "money");
    const weekday = weekdayOf(day);
    const date = Number(day.slice(8));
    const between = (low: number, high: number) => Math.round((low + draw() * (high - low)) / 10) * 10;
    const morning = day === today;
    const add = (preset: Preset, note: string, rubles: number, early = false) => {
      if (!morning || early) found.push({ amount: rubles * 100, category_id: categoryOf(preset), note, day });
    };
    if (draw() < 0.35) add("cafe", words.coffee, between(180, 260), true);
    if (weekday < 5 && draw() < 0.6) add("transport", words.metro, 72, true);
    if (weekday < 5 && draw() < 0.15) add("cafe", words.lunch, between(350, 450));
    if (draw() < 0.3) add("groceries", words.groceries, between(600, 1600));
    if (draw() < 0.06) add("transport", words.taxi, between(350, 650));
    if (weekday >= 5 && draw() < 0.3) add("fun", words.cinema, between(450, 650));
    if (draw() < 0.05) add("health", words.pharmacy, between(300, 800));
    if (date === 10) add("phone", words.phone, 650);
    if (date === 15) add("subscriptions", words.subscription, 399);
    if (date === clothesDay(day.slice(0, 7), language)) add("clothes", words.clothes, between(2500, 4000));
    if (date === 5) add("salary", words.job, 20_000);
    if (date === 25) add("stipend", words.stipend, 3200);
  }
  return found;
}

/**
 * The budget warnings the seeded month has set off already: money_month.alerts_after would have
 * shown them as the spending crossed the thresholds, and they warn only once a month.
 */
function shownAlerts(data: Data, today: string): Set<string> {
  const month = today.slice(0, 7);
  const expenses = data.entries.filter((entry) =>
    entry.day.startsWith(month)
    && data.categories.find((category) => category.id === entry.category_id)?.kind === "expense");
  const shown = new Set<string>();
  const budgets: [number, number | null][] = [
    [0, data.profile.budget], ...data.categories.map((category): [number, number | null] => [category.id, category.budget]),
  ];
  for (const [scope, budget] of budgets) {
    if (budget === null) continue;
    const spent = expenses
      .filter((entry) => scope === 0 || entry.category_id === scope)
      .reduce((sum, entry) => sum + entry.amount, 0);
    for (const threshold of [80, 100]) if (spent * 100 >= budget * threshold) shown.add(`${month}/${scope}/${threshold}`);
  }
  return shown;
}

export function seed(language: Lang, moment: number): Data {
  // The minute of the moment: the host seeds a few milliseconds after ?at=, and they must not move
  // what is laid out from now (at 10:30 the parcel is at 12:00, a millisecond later it would be 12:30).
  const now = Math.floor(moment / MINUTE) * MINUTE;
  const words = SEED_WORDS[language];
  const today = localDay(ZONE, now);
  let item = 0;
  const cities: WeatherCity[] = EXTRA.map((geoId, index) => {
    const { name, admin, country, lat, lon, timezone } = placeOut(knownPlace(geoId), language);
    return { id: index + 1, name, admin: admin ?? null, country: country ?? null, lat, lon, timezone, geo_id: geoId };
  });
  const categories: StoredCategory[] = PRESETS.map(([preset, kind, emoji], index) => ({
    id: index + 1, kind, preset, name: null, emoji, hidden: false, budget: CATEGORY_BUDGETS[preset] ?? null,
  }));
  const categoryOf = (preset: Preset) => categories.find((category) => category.preset === preset)?.id ?? 0;
  const timetable: Lesson[] = words.lessons.map(([weekday, start, end, title, kind, room]) => ({
    weekday, start, end, title, kind, room,
  }));
  const data: Data = {
    profile: {
      first_name: WORDS[language].name,
      language: "auto",
      home: { name: WORDS[language].home, lat: HOME.lat, lon: HOME.lon, timezone: ZONE },
      morning: { enabled: true, time: "08:00" },
      can_write: true,
      currency: "RUB",
      budget: BUDGET,
    },
    cities,
    notes: notes(words.notes, now, () => (item += 1)),
    reminders: reminders(words.reminders, now),
    habits: [
      habit(1, "sport", words.habits.sport, { emoji: "💪", color: "mint", weekly_goal: DAILY }, 400, 0.82, today, language),
      habit(2, "reading", words.habits.reading, { emoji: "📚", color: "violet", weekly_goal: DAILY }, 220, 0.9, today, language),
      habit(3, "swimming", words.habits.swimming, { emoji: "🏊", color: "sky", weekly_goal: 3 }, 300, 0.85, today, language),
      habit(4, "sugar", words.habits.sugar, { emoji: "🍎", color: "amber", weekly_goal: DAILY }, 21, 0.85, today, language),
    ],
    categories,
    entries: spending(language, today, categoryOf).map((entry, index) => ({ id: index + 1, ...entry })),
    alerts: new Set(),
    source: { kind: "mirea", title: words.group, mirea_id: GROUP_ID, url: null, fetched: now - 2 * HOUR, minutes: 10 },
    timetable,
    group: { id: GROUP_ID, name: words.group },
    next: { note: 0, item: 0, city: 0, reminder: 0, habit: 0, entry: 0, category: 0 },
    shared: 0,
  };
  data.alerts = shownAlerts(data, today);
  const after = (list: { id: number }[]) => Math.max(0, ...list.map((record) => record.id)) + 1;
  data.next = {
    note: after(data.notes), item: item + 1, city: after(data.cities), reminder: after(data.reminders),
    habit: after(data.habits), entry: after(data.entries), category: after(data.categories),
  };
  return data;
}
