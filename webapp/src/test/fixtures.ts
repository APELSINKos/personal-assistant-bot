import type {
  Forecast, ForecastHour, Habit, Me, MoneyCategory, MoneyMonth, Note, Reminder, ScheduleSource, Today, WeatherCity,
} from "../api/types";

export const me: Me = {
  id: 1,
  first_name: "Alex",
  language: "ru",
  language_setting: "auto",
  city: { name: "Москва", lat: 55.75, lon: 37.62, timezone: "Europe/Moscow" },
  morning: { enabled: true, time: "08:00" },
  can_write: true,
  currency: "RUB",
  money_budget: null,
};

export const habit: Habit = {
  id: 7,
  name: "Спорт",
  emoji: "💪",
  color: "mint",
  weekly_goal: 7,
  created_on: "2026-09-12",
  done_today: null,
  streak: 5,
  streak_unit: "days",
  record: 9,
  percent: 71,
  week_done: 0,
  week_goal: 7,
  week: "-......",
  done_days: 12,
  total_days: 17,
  last_days: [true, true, false, true, true, true, true, true, null],
};

export const today: Today = {
  date: "2026-09-28",
  part_of_day: "day",
  weather: {
    city: "Москва", temperature: 9.6, feels_like: 7.2, wind: 3.4, code: 1, emoji: "🌤",
    description: "малооблачно", tmin: 5.8, tmax: 13.2,
    tips: ["☔ Дождь ожидается после 18:00 — зонт сегодня пригодится", "🧥 Утром холодно"],
  },
  reminders_today: [{ id: 3, text: "Созвон", time: "19:30", due_at: "2026-09-28T16:30:00Z" }],
  habits: { done: 0, total: 1, items: [habit] },
  notes_count: 4,
  rates: {
    date: "2026-09-28", usd: { value: 84.1975, change: -0.3118 }, eur: { value: 96.6671, change: 0.2 },
  },
  best_streak: { name: "Спорт", count: 5, unit: "days" },
  has_schedule: false,
  lessons: [],
  week_label: null,
  money: null,
  tomorrow: null,
  classes_weather: null,
  pinned_notes: [],
};

export const note: Note = {
  id: 11, text: "Купить хлеб", pinned: false, items: [],
  created_at: "2026-09-27T10:00:00Z", updated_at: "2026-09-27T10:00:00Z",
};

/** A pinned checklist: milk still to buy, bread bought. */
export const checklist: Note = {
  id: 12, text: "Покупки", pinned: true,
  items: [{ id: 31, text: "молоко", done: false }, { id: 32, text: "хлеб", done: true }],
  created_at: "2026-09-26T09:00:00Z", updated_at: "2026-09-26T09:00:00Z",
};

/** An hour of the server's stub day (tests/stubs.py): 5.8 at 05:00, 13.2 at 15:00. */
const DAY_TEMPERATURES = [
  7.0, 6.6, 6.3, 6.1, 5.9, 5.8, 6.0, 6.6, 7.6, 8.8, 9.9, 11.0,
  11.9, 12.6, 13.1, 13.2, 13.0, 12.4, 11.6, 10.6, 9.6, 8.8, 8.1, 7.5,
];

/** The 23 hours after 15:00: the evening, the night with the moon, the next day to 14:00; rain likely at 21:00. */
const HOURS: ForecastHour[] = Array.from({ length: 23 }, (_, index) => {
  const hour = (16 + index) % 24;
  const night = hour < 7 || hour > 18;
  return {
    time: `${String(hour).padStart(2, "0")}:00`,
    emoji: night ? "🌙" : "🌤",
    description: "малооблачно",
    temperature: DAY_TEMPERATURES[hour] ?? 0,
    precip_chance: hour === 21 ? 40 : 0,
  };
});

/** Moscow at 15:00 on Monday, 28 September 2026, as GET /weather gives it. */
export const forecast: Forecast = {
  city: { id: 0, name: "Москва", home: true },
  now: {
    temperature: 9.6, feels_like: 7.2, wind: 3.4, gusts: 6.1, humidity: 71, is_day: true,
    emoji: "🌤", description: "малооблачно", precip_chance: 0,
  },
  tips: ["🚲 Сегодня хороший день для велосипеда"],
  hours: HOURS,
  days: [
    { date: "2026-09-28", emoji: "🌤", description: "малооблачно", tmin: 5.8, tmax: 13.2, precip_chance: 0 },
    { date: "2026-09-29", emoji: "🌧", description: "дождь", tmin: 6.1, tmax: 11.0, precip_chance: 80 },
    { date: "2026-09-30", emoji: "☁️", description: "пасмурно", tmin: 4.9, tmax: 9.7, precip_chance: 10 },
    { date: "2026-10-01", emoji: "☀️", description: "ясно", tmin: 3.2, tmax: 12.4, precip_chance: 0 },
    { date: "2026-10-02", emoji: "🌤", description: "малооблачно", tmin: 5.0, tmax: 14.1, precip_chance: null },
    { date: "2026-10-03", emoji: "🌦", description: "морось", tmin: 7.3, tmax: 12.0, precip_chance: 20 },
    { date: "2026-10-04", emoji: "☁️", description: "пасмурно", tmin: 6.4, tmax: 10.8, precip_chance: 0 },
  ],
  sunrise: "06:40",
  sunset: "18:40",
  polar: null,
};

/** An extra city of the weather (GET /me/cities). */
export const tula: WeatherCity = {
  id: 3, name: "Тула", admin: "Тульская область", country: "Россия",
  lat: 54.19, lon: 37.62, timezone: "Europe/Moscow", geo_id: 480562,
};

export const reminder: Reminder = {
  id: 3, text: "Созвон", due_at: "2026-09-28T16:30:00Z", due_local: "2026-09-28T19:30", status: "pending",
  repeat: "none", rule: null, description: null,
};

export const scheduleSource: ScheduleSource = {
  kind: "mirea", title: "ИКБО-63-24", mirea_id: 4805,
  url: "https://english.mirea.ru/schedule/api/ical/1/4805",
  fetched_at: "2026-09-28T12:00:00Z", ok_at: "2026-09-28T12:00:00Z", error: null, stale: false,
  lesson_reminder_minutes: null, lessons_ahead: 36,
};

export const moneyCategories: MoneyCategory[] = [
  { id: 1, kind: "expense", name: "Продукты", emoji: "🛒", hidden: false, can_hide: true, budget: null },
  { id: 2, kind: "expense", name: "Кафе", emoji: "☕", hidden: false, can_hide: true, budget: 500000 },
  { id: 3, kind: "expense", name: "Транспорт", emoji: "🚌", hidden: false, can_hide: true, budget: null },
  { id: 4, kind: "expense", name: "Дом", emoji: "🏠", hidden: false, can_hide: true, budget: null },
  { id: 5, kind: "expense", name: "Одежда", emoji: "👕", hidden: true, can_hide: true, budget: null },
  { id: 6, kind: "expense", name: "Другое", emoji: "📦", hidden: false, can_hide: false, budget: null },
  { id: 7, kind: "income", name: "Стипендия", emoji: "🎓", hidden: false, can_hide: true, budget: null },
  { id: 8, kind: "income", name: "Другое", emoji: "💰", hidden: false, can_hide: false, budget: null },
];

/** September 2026 on the 28th: rent on the 1st, food and a taxi yesterday, coffee today. */
export const moneyMonth: MoneyMonth = {
  month: "2026-09",
  first_month: "2026-08",
  currency: "RUB",
  spent: 1698050,
  income: 300000,
  balance: -1398050,
  budget: 3000000,
  left: 1301950,
  per_day: 433983,
  expenses: [
    { category_id: 4, amount: 1500000, share: 88, left: null },
    { category_id: 1, amount: 125000, share: 7, left: null },
    { category_id: 2, amount: 43050, share: 3, left: 456950 },
    { category_id: 3, amount: 30000, share: 2, left: null },
  ],
  incomes: [{ category_id: 7, amount: 300000, share: 0, left: null }],
  days: [1500000, ...Array<number>(25).fill(0), 155000, 43050, null, null],
  categories: moneyCategories,
  entries: [
    { id: 24, amount: 43050, category_id: 2, note: "кофе", day: "2026-09-28" },
    { id: 23, amount: 30000, category_id: 3, note: "такси", day: "2026-09-27" },
    { id: 22, amount: 125000, category_id: 1, note: "", day: "2026-09-27" },
    { id: 21, amount: 300000, category_id: 7, note: "", day: "2026-09-25" },
    { id: 20, amount: 1500000, category_id: 4, note: "аренда", day: "2026-09-01" },
  ],
};
