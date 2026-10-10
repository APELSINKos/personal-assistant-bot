/**
 * The demo's data at the start of a visit (spec §5.2, §5.3, §23.4): the made-up user «Саша» / «Alex»
 * in Moscow, in the language the demo was opened in. What a day holds — the marks of the habits, the
 * money spent — comes from a hash of the date, so a past day stays as it was from one visit to the
 * next and the same minute gives the same data; reminders and notes are laid out from that minute.
 */
import type { MoneyEntry, NoteItem, RepeatRule, WeatherCity } from "../../api/types";
import type { Lang } from "../../i18n";
import { addDaysIso, mondayOf } from "../../lib/format";
import { DAILY } from "../../lib/habits";
import type { Data, Lesson, Preset, StoredCategory, StoredHabit, StoredNote, StoredReminder } from "./data";
import { knownPlace, placeOut } from "./places";
import { chance, draws } from "./random";
import { WEEKDAYS } from "./recurrence";
import { HOUR, localDay, momentOf, monthStart, MINUTE, nextMonth, weekdayOf } from "./time";
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
/** The budgets of the month, in roubles: all expenses and two categories. */
const BUDGET = 30_000;
const CATEGORY_BUDGETS: Partial<Record<Preset, number>> = { cafe: 4000, fun: 3000 };
/** What a whole month's expenses come to: about 85 % of the budget, a little more or less each month. */
const MONTH_SHARE = [0.83, 0.87] as const;
/** «Кафе» comes to at most this share of its budget: under 80 %, so a month warns only of all its expenses. */
const CAFE_MOST = 0.77;
/** The cinema at most so many times a month: «Развлечения» stays under 80 % of its budget too. */
const CINEMA_VISITS = 3;
/** The month's income, in roubles: the part-time job on the 5th and the stipend on the 25th, more than any month spends. */
const JOB = 25_000;
const STIPEND = 3500;

/** The demo's group in MIREA's directory: any search finds it. */
const GROUP_ID = 4242;

/**
 * The notes of §23.4 in their order, each made after the one before it: how many hours ago it was
 * made and, for the three pinned ones, pinned. The shopping list was pinned last, so it comes first.
 */
const NOTE_HOURS: readonly (readonly [made: number, pinned: number | null])[] = [
  [336, 3], [216, 48], [192, 192], [150, null], [120, null], [96, null], [50, null], [20, null],
];

function notes(language: Lang, now: number, item: () => number): StoredNote[] {
  const words = SEED_WORDS[language].notes;
  const checklist = (texts: readonly string[], done: number): NoteItem[] =>
    texts.map((text, index) => ({ id: item(), text, done: index < done }));
  const contents: [string, NoteItem[]][] = [
    [WORDS[language].shopping, checklist(words.shoppingItems, 3)],
    [words.packing, checklist(words.packingItems, 4)],
    [words.door, []], [words.gifts, []], [words.reading, []], [words.pancakes, []], [words.coursework, []],
    [words.debt, []],
  ];
  return contents.map(([text, items], index) => {
    const [made = 0, pinned = null] = NOTE_HOURS[index] ?? [];
    return {
      id: index + 1, text, created: now - made * HOUR, updated: now - made * HOUR,
      pinned: pinned === null ? null : now - pinned * HOUR, items,
    };
  });
}

/** The first :00 or :30 at least `ahead` after `now`. */
const halfHourAfter = (now: number, ahead: number) => Math.ceil((now + ahead) / (30 * MINUTE)) * 30 * MINUTE;

function reminders(words: SeedWords["reminders"], now: number): StoredReminder[] {
  const today = localDay(ZONE, now);
  const anchor = addDaysIso(today, -30);
  const rule = (repeat: RepeatRule["repeat"], time: string, more: Partial<RepeatRule> = {}): RepeatRule => ({
    repeat, time_local: time, weekdays: null, interval_weeks: 1, month_day: null, anchor_date: anchor, ...more,
  });
  // Two of today's: at the first :00 or :30 an hour and a half ahead and four hours ahead, while that is still today.
  const todays = ([[1, words.parcel, 90 * MINUTE], [2, words.call, 4 * HOUR]] as const).flatMap(([id, text, ahead]) => {
    const due = halfHourAfter(now, ahead);
    return localDay(ZONE, due) === today ? [{ id, text, due, rule: null }] : [];
  });
  return [
    ...todays,
    { id: 3, text: words.lab, due: momentOf(ZONE, addDaysIso(today, 1), "10:00"), rule: null },
    { id: 4, text: words.dentist, due: momentOf(ZONE, addDaysIso(today, 3), "19:00"), rule: null },
    { id: 5, text: words.water, due: null, rule: rule("daily", "08:00") },
    { id: 6, text: words.workout, due: null, rule: rule("weekly", "07:30", { weekdays: WEEKDAYS }) },
    // Tuesdays and Thursdays every other week, from a Tuesday four weeks back: this week is one of its weeks.
    {
      id: 7, text: words.plants, due: null,
      rule: rule("weekly", "18:00", { weekdays: 0b0001010, interval_weeks: 2, anchor_date: addDaysIso(mondayOf(today), -27) }),
    },
    { id: 8, text: words.phone, due: null, rule: rule("monthly", "12:00", { month_day: 10 }) },
  ];
}

/** How far back the story of §5.3 goes: today and the 9 days before it. */
const STORY_DAYS = 9;

/** The marks a habit's story sets, by days before today; null leaves a day without a mark. */
type Story = readonly (readonly [back: number, mark: boolean | null])[];

/**
 * A habit's marks from the day it began up to today. Every day draws its mark from its date (spec
 * §5.2): done at `rate`, otherwise missed or left unmarked, the same on every visit; a weekly habit is
 * marked on Mondays, Wednesdays and Fridays, and today is left open. Then today and the 9 days before
 * it tell the story of §5.3 — «Спорт» done the last 9 days and open today, «Читать» done today, «Без
 * сахара» missed yesterday — and the story wins over those days' draws: it is what the screens show.
 * An older day always keeps its draw, so a day the story set while it was recent shows its own draw
 * to a visit ten days later. One ?at gives the same marks on every load.
 */
function habit(
  id: number, key: string, name: string, look: Pick<StoredHabit, "emoji" | "color" | "weekly_goal">,
  age: number, rate: number, story: Story, today: string, language: Lang,
): StoredHabit {
  const marks = new Map<string, boolean>();
  for (let back = age; back >= 1; back -= 1) {
    const day = addDaysIso(today, -back);
    if (look.weekly_goal !== DAILY && ![0, 2, 4].includes(weekdayOf(day))) continue;
    const draw = draws(day, language, "habit", key);
    if (draw() < rate) marks.set(day, true);
    else if (draw() < 0.6) marks.set(day, false);
  }
  for (const [back, mark] of story) {
    if (back > Math.min(age, STORY_DAYS)) continue;
    const day = addDaysIso(today, -back);
    if (mark === null) marks.delete(day);
    else marks.set(day, mark);
  }
  return { id, name, ...look, created_on: addDaysIso(today, -age), marks };
}

/** An entry of a month's plan, in roubles; `early` is what a morning already has. */
interface Planned {
  day: string;
  preset: Preset;
  note: string;
  rubles: number;
  early: boolean;
}

/** Round to tens of roubles, as people remember what they paid. */
const tens = (rubles: number) => Math.round(rubles / 10) * 10;

/**
 * A month's money, planned whole (spec §5.3). Each day's draws say what was bought — coffee, lunch,
 * groceries, the metro, a taxi, the cinema, the chemist's — and for how much; the phone is paid on
 * the 10th, the subscription on the 15th, clothes are bought once a month; the job pays on the 5th
 * and the stipend comes on the 25th. A month heavy on coffee and lunches is shaved down to «Кафе»'s
 * share, and the groceries share what is left of about 85 % of the month's budget: the month crosses
 * 80 % only at its end, and it never spends more than it earns. All of it comes from the month's
 * dates, so a past day keeps its money.
 */
function monthPlan(first: string, language: Lang): Planned[] {
  const words = SEED_WORDS[language].money;
  const month = first.slice(0, 7);
  const clothes = 1 + Math.floor(chance(month, language, "clothes") * 27);
  const plan: Planned[] = [];
  const cafe: Planned[] = [];
  const groceries: { entry: Planned; weight: number }[] = [];
  let cinema = 0;
  let sinceGroceries = 3;
  for (let day = first; day < nextMonth(first); day = addDaysIso(day, 1)) {
    const draw = draws(day, language, "money");
    const weekday = weekdayOf(day);
    const date = Number(day.slice(8));
    const between = (low: number, high: number) => tens(low + draw() * (high - low));
    const add = (preset: Preset, note: string, rubles: number, early = false): Planned => {
      const entry = { day, preset, note, rubles, early };
      plan.push(entry);
      return entry;
    };
    if (draw() < 0.25) cafe.push(add("cafe", words.coffee, between(180, 260), true));
    if (weekday < 5 && draw() < 0.6) add("transport", words.metro, 72, true);
    if (weekday < 5 && draw() < 0.1) cafe.push(add("cafe", words.lunch, between(350, 450)));
    // Groceries every few days: at least every fifth.
    sinceGroceries += 1;
    if (draw() < 0.3 || sinceGroceries > 4) {
      groceries.push({ entry: add("groceries", words.groceries, 0), weight: 0.6 + draw() * 0.8 });
      sinceGroceries = 0;
    }
    if (draw() < 0.06) add("transport", words.taxi, between(350, 650));
    if (weekday >= 5 && draw() < 0.3 && cinema < CINEMA_VISITS) {
      cinema += 1;
      add("fun", words.cinema, between(450, 650));
    }
    if (draw() < 0.05) add("health", words.pharmacy, between(300, 800));
    if (date === 10) add("phone", words.phone, 650);
    if (date === 15) add("subscriptions", words.subscription, 399);
    if (date === clothes) add("clothes", words.clothes, between(2500, 4000));
    if (date === 5) add("salary", words.job, JOB);
    if (date === 25) add("stipend", words.stipend, STIPEND);
  }
  const sum = (entries: readonly Planned[]) => entries.reduce((total, entry) => total + entry.rubles, 0);
  const shave = Math.min(1, ((CATEGORY_BUDGETS.cafe ?? 0) * CAFE_MOST) / Math.max(sum(cafe), 1));
  for (const entry of cafe) entry.rubles = tens(entry.rubles * shave);
  const others = sum(plan.filter((entry) => entry.preset !== "groceries" && !["salary", "stipend"].includes(entry.preset)));
  const [low, high] = MONTH_SHARE;
  const left = BUDGET * (low + chance(month, language, "month") * (high - low)) - others;
  const weights = groceries.reduce((total, { weight }) => total + weight, 0);
  for (const { entry, weight } of groceries) entry.rubles = tens((left * weight) / weights);
  return plan;
}

/** The money of the visitor from the first day of the month before last up to today: today only what a morning has. */
function spending(language: Lang, today: string, categoryOf: (preset: Preset) => number): Omit<MoneyEntry, "id">[] {
  const found: Omit<MoneyEntry, "id">[] = [];
  const monthBefore = (first: string) => monthStart(addDaysIso(first, -1));
  for (let first = monthBefore(monthBefore(monthStart(today))); first <= today; first = nextMonth(first)) {
    for (const { day, preset, note, rubles, early } of monthPlan(first, language)) {
      if (day > today || (day === today && !early)) continue;
      found.push({ amount: rubles * 100, category_id: categoryOf(preset), note, day });
    }
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
  const categories: StoredCategory[] = PRESETS.map(([preset, kind, emoji], index) => {
    const budget = CATEGORY_BUDGETS[preset];
    return { id: index + 1, kind, preset, name: null, emoji, hidden: false, budget: budget === undefined ? null : budget * 100 };
  });
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
      budget: BUDGET * 100,
    },
    cities,
    notes: notes(language, now, () => (item += 1)),
    reminders: reminders(words.reminders, now),
    habits: [
      habit(1, "sport", words.habits.sport, { emoji: "💪", color: "mint", weekly_goal: DAILY }, 400, 0.82, [
        [0, null], ...Array.from({ length: STORY_DAYS }, (_, index) => [index + 1, true] as const),
      ], today, language),
      habit(
        2, "reading", words.habits.reading, { emoji: "📚", color: "violet", weekly_goal: DAILY }, 220, 0.9, [[0, true]],
        today, language,
      ),
      habit(3, "swimming", words.habits.swimming, { emoji: "🏊", color: "sky", weekly_goal: 3 }, 300, 0.85, [], today, language),
      habit(
        4, "sugar", words.habits.sugar, { emoji: "🍎", color: "amber", weekly_goal: DAILY }, 21, 0.85, [[1, false]],
        today, language,
      ),
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
