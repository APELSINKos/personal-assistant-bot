import type { Habit, Me, Note, Reminder, ScheduleSource, Today } from "../api/types";

export const me: Me = {
  id: 1,
  first_name: "Alex",
  language: "ru",
  language_setting: "auto",
  city: { name: "Москва", lat: 55.75, lon: 37.62, timezone: "Europe/Moscow" },
  morning: { enabled: true, time: "08:00" },
  can_write: true,
};

export const habit: Habit = {
  id: 7,
  name: "Спорт",
  created_on: "2026-09-12",
  done_today: null,
  streak: 5,
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
  best_streak: { name: "Спорт", days: 5 },
  has_schedule: false,
  lessons: [],
  week_label: null,
};

export const note: Note = {
  id: 11, text: "Купить хлеб", created_at: "2026-09-27T10:00:00Z", updated_at: "2026-09-27T10:00:00Z",
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
