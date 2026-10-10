import { describe, expect, it } from "vitest";
import type { Lang } from "../../i18n";
import { addDaysIso } from "../../lib/format";
import type { Data, StoredHabit } from "./data";
import { seed } from "./seeds";
import { DAY, localDay, MINUTE, monthLength } from "./time";

// Wednesday 7 October 2026, 10:30 in Moscow.
const MORNING = Date.UTC(2026, 9, 7, 7, 30);
const ZONE = "Europe/Moscow";

/** The habit of the story: «Спорт», «Читать 20 страниц», «Бассейн», «Без сахара» in their order. */
function habitsOf(data: Data): [StoredHabit, StoredHabit, StoredHabit, StoredHabit] {
  const [sport, reading, swimming, sugar] = data.habits;
  if (!sport || !reading || !swimming || !sugar) throw new Error("Four habits are seeded");
  return [sport, reading, swimming, sugar];
}

/** A month's money as the money screen sums it: expenses, incomes, and by category, in roubles. */
function monthOf(data: Data, month: string) {
  const kind = (id: number) => data.categories.find((category) => category.id === id);
  const entries = data.entries.filter((entry) => entry.day.startsWith(month));
  const sum = (list: typeof entries) => list.reduce((total, entry) => total + entry.amount, 0) / 100;
  const expenses = entries.filter((entry) => kind(entry.category_id)?.kind === "expense");
  const byPreset = (preset: string) => sum(expenses.filter((entry) => kind(entry.category_id)?.preset === preset));
  // The day the month's expenses first reach 80 % of the budget.
  let spent = 0;
  let warned: string | null = null;
  for (const entry of [...expenses].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0))) {
    spent += entry.amount / 100;
    if (warned === null && spent >= 24_000) warned = entry.day;
  }
  return {
    spent: sum(expenses), income: sum(entries.filter((entry) => kind(entry.category_id)?.kind === "income")),
    cafe: byPreset("cafe"), fun: byPreset("fun"), warned,
  };
}

describe("the demo's data", () => {
  it("are the same for the same moment: one ?at=, one picture", () => {
    expect(seed("ru", MORNING)).toEqual(seed("ru", MORNING));
    expect(seed("en", MORNING)).toEqual(seed("en", MORNING));
  });

  it("are the same all through the minute of ?at=: the host seeds a moment after it", () => {
    for (const language of ["ru", "en"] as const) {
      const first = seed(language, MORNING);
      expect(seed(language, MORNING + 1), language).toEqual(first);
      expect(seed(language, MORNING + 59_999), language).toEqual(first);
    }
    // The parcel and the call: the first :00 or :30 at least an hour and a half, and four hours, ahead of the minute.
    const today = (moment: number) => seed("ru", moment).reminders.filter((reminder) => reminder.id <= 2).map((reminder) => reminder.due);
    expect(today(MORNING + 1)).toEqual([Date.UTC(2026, 9, 7, 9, 0), Date.UTC(2026, 9, 7, 11, 30)]);
    expect(today(MORNING + MINUTE)).toEqual([Date.UTC(2026, 9, 7, 9, 30), Date.UTC(2026, 9, 7, 12, 0)]);
  });

  it("tell §5.3's story for today and the 9 days before it, and keep each older day as its date draws it", () => {
    for (const [language, moment] of [["ru", MORNING], ["en", MORNING + 40 * DAY], ["ru", Date.UTC(2027, 0, 15, 9)]] as const) {
      const today = localDay(ZONE, moment);
      const [sport, reading, swimming, sugar] = habitsOf(seed(language, moment));
      const back = (days: number) => addDaysIso(today, -days);
      // «Спорт»: the last 9 days done, today open; «Читать»: done today; «Без сахара»: missed yesterday.
      expect(Array.from({ length: 9 }, (_, index) => sport.marks.get(back(index + 1))), today).toEqual(Array(9).fill(true));
      expect([sport, reading, swimming, sugar].map((habit) => habit.marks.get(today) ?? null), today)
        .toEqual([null, true, null, null]);
      expect(sugar.marks.get(back(1)), today).toBe(false);
    }
    // A day older than the story's ten keeps the mark its date draws. Visits 12 and 30 days later agree on
    // the days the first visit's story told — there «Спорт» was done each day — and on every older one.
    const between = (habit: StoredHabit | undefined, from: string, to: string) =>
      [...(habit?.marks ?? [])].filter(([day]) => from <= day && day < to).sort(([a], [b]) => (a < b ? -1 : 1));
    const [first, later, latest] = [MORNING, MORNING + 12 * DAY, MORNING + 30 * DAY].map((moment) => habitsOf(seed("ru", moment)));
    expect(between(first?.[0], "2026-09-28", "2026-10-07").map(([, done]) => done)).toEqual(Array(9).fill(true));
    // «Спорт», «Читать» and «Бассейн» began long before: «Без сахара» began three weeks before each visit.
    for (let index = 0; index < 3; index += 1) {
      const told = between(later?.[index], "2026-09-28", "2026-10-07");
      expect(between(latest?.[index], "2026-09-28", "2026-10-07"), latest?.[index]?.name).toEqual(told);
      const older = between(first?.[index], latest?.[index]?.created_on ?? "", "2026-09-28");
      expect(older.length).toBeGreaterThan(50);
      expect(between(later?.[index], latest?.[index]?.created_on ?? "", "2026-09-28"), later?.[index]?.name).toEqual(older);
      expect(between(latest?.[index], latest?.[index]?.created_on ?? "", "2026-09-28"), latest?.[index]?.name).toEqual(older);
    }
  });

  it("keep a past day's money as it was and give each new day its own", () => {
    const today = seed("ru", MORNING);
    const later = seed("ru", MORNING + 3 * DAY);
    const spent = (data: Data) =>
      data.entries.filter((entry) => entry.day < "2026-10-07").map(({ amount, note, day }) => [day, note, amount]);
    expect(spent(later).filter(([day]) => String(day) >= "2026-08-01")).toEqual(spent(today));
    expect(later.entries.some((entry) => entry.day > addDaysIso("2026-10-07", 1))).toBe(true);
  });

  it("are the visitor's, in the language the demo was opened in", () => {
    const ru = seed("ru", MORNING);
    expect(ru.profile).toEqual({
      first_name: "Саша", language: "auto",
      home: { name: "Москва", lat: 55.75222, lon: 37.61556, timezone: "Europe/Moscow" },
      morning: { enabled: true, time: "08:00" }, can_write: true, currency: "RUB", budget: 3_000_000,
    });
    expect(ru.cities.map((city) => city.name)).toEqual(["Тула", "Петропавловск-Камчатский", "Ереван"]);
    expect(ru.group.name).toBe("ДЕМО-01-26");
    const en = seed("en", MORNING);
    expect(en.profile.first_name).toBe("Alex");
    expect(en.profile.home.name).toBe("Moscow");
    expect(en.cities.map((city) => city.name)).toEqual(["Tula", "Petropavlovsk-Kamchatsky", "Yerevan"]);
    expect(en.habits.map((habit) => habit.name)).toEqual(["Sport", "Read 20 pages", "Swimming", "No sugar"]);
    expect(en.timetable.every((lesson) => lesson.kind === null)).toBe(true);
  });

  it("hold the eight notes of §23.4, the three pinned ones with the shopping list on top", () => {
    const checklist = (data: Data, id: number) =>
      data.notes.find((note) => note.id === id)?.items.map((item) => `${item.done ? "✅ " : ""}${item.text}`);
    const ru = seed("ru", MORNING);
    expect(ru.notes.map((note) => [note.id, note.text])).toEqual([
      [1, "Покупки"], [2, "Собрать в поездку"], [3, "Код домофона: 45В7"],
      [4, "Идеи подарков: маме — плед, брату — настольная игра, бабушке — фотоальбом"],
      [5, "Почитать осенью: что-нибудь о космосе, сборник рассказов, книгу о дизайне интерфейсов"],
      [6, "Блины: 2 яйца, 500 мл молока, 200 г муки, щепотка соли, ложка сахара"],
      [7, "Курсовая: план до 20 октября, источники — https://example.com/library"],
      [8, "Вернуть Диме 1 500 ₽ до пятницы"],
    ]);
    expect(checklist(ru, 1)).toEqual(["✅ молоко", "✅ хлеб", "✅ яйца", "сыр", "яблоки", "кофе", "макароны"]);
    expect(checklist(ru, 2)).toEqual([
      "✅ паспорт", "✅ зарядка", "✅ наушники", "✅ зонт", "свитер", "зубная щётка", "книга", "билеты",
    ]);
    // Pinned: the shopping list last, so first in every list; each note made after the one before it.
    const pinned = ru.notes.filter((note) => note.pinned !== null).sort((a, b) => (b.pinned ?? 0) - (a.pinned ?? 0));
    expect(pinned.map((note) => note.id)).toEqual([1, 2, 3]);
    expect(ru.notes.every((note, index) => index === 0 || note.created > (ru.notes[index - 1]?.created ?? 0))).toBe(true);
    expect(ru.notes.every((note) => note.created <= MORNING && (note.pinned ?? note.created) >= note.created)).toBe(true);

    const en = seed("en", MORNING);
    expect(en.notes.map((note) => note.text)).toEqual([
      "Shopping", "Packing list", "Door code: 45B7",
      "Gift ideas: a blanket for Mum, a board game for my brother, a photo album for Grandma",
      "To read this autumn: something about space, a short story collection, a book on interface design",
      "Pancakes: 2 eggs, 500 ml of milk, 200 g of flour, a pinch of salt, a spoonful of sugar",
      "Coursework: the outline by October 20, sources — https://example.com/library",
      "Pay Dima back 1,500 ₽ by Friday",
    ]);
    expect(checklist(en, 1)).toEqual(["✅ milk", "✅ bread", "✅ eggs", "cheese", "apples", "coffee", "pasta"]);
    expect(checklist(en, 2)).toEqual([
      "✅ passport", "✅ charger", "✅ earphones", "✅ umbrella", "sweater", "toothbrush", "book", "tickets",
    ]);
  });

  it("hold the eight reminders of §5.3: two today while there is time, then the week, then the repeats", () => {
    const ru = seed("ru", MORNING);
    expect(ru.reminders.map((reminder) => [reminder.id, reminder.text, reminder.due, reminder.rule])).toEqual([
      [1, "Забрать посылку", Date.UTC(2026, 9, 7, 9, 0), null],
      [2, "Созвон по курсовой", Date.UTC(2026, 9, 7, 11, 30), null],
      [3, "Сдать лабораторную", Date.UTC(2026, 9, 8, 7, 0), null],
      [4, "Записаться к стоматологу", Date.UTC(2026, 9, 10, 16, 0), null],
      [5, "Выпить воды", null, {
        repeat: "daily", time_local: "08:00", weekdays: null, interval_weeks: 1, month_day: null, anchor_date: "2026-09-07",
      }],
      [6, "Зарядка", null, {
        repeat: "weekly", time_local: "07:30", weekdays: 31, interval_weeks: 1, month_day: null, anchor_date: "2026-09-07",
      }],
      // Every other week from a Tuesday four weeks back: this week is one of its weeks.
      [7, "Полить цветы", null, {
        repeat: "weekly", time_local: "18:00", weekdays: 2 | 8, interval_weeks: 2, month_day: null, anchor_date: "2026-09-08",
      }],
      [8, "Оплатить телефон", null, {
        repeat: "monthly", time_local: "12:00", weekdays: null, interval_weeks: 1, month_day: 10, anchor_date: "2026-09-07",
      }],
    ]);
    expect(seed("en", MORNING).reminders.map((reminder) => reminder.text)).toEqual([
      "Pick up the parcel", "Coursework call", "Hand in the lab report", "Book a dentist appointment", "Drink water",
      "Workout", "Water the plants", "Pay the phone bill",
    ]);
    // In the evening the call no longer fits into the day, and late at night neither does the parcel.
    const evening = seed("ru", Date.UTC(2026, 9, 7, 17, 30)).reminders.map((reminder) => reminder.id);
    expect(evening).toEqual([1, 3, 4, 5, 6, 7, 8]);
    expect(seed("ru", Date.UTC(2026, 9, 7, 19, 31)).reminders.map((reminder) => reminder.id)).toEqual([3, 4, 5, 6, 7, 8]);
  });

  it("give every record its own id and the next one after them", () => {
    const data = seed("ru", MORNING);
    const ids = (list: { id: number }[]) => list.map((item) => item.id);
    for (const [kind, list] of [
      ["note", data.notes], ["city", data.cities], ["reminder", data.reminders], ["habit", data.habits],
      ["entry", data.entries], ["category", data.categories],
    ] as const) {
      expect(new Set(ids(list)).size, kind).toBe(list.length);
      expect(data.next[kind], kind).toBeGreaterThan(Math.max(0, ...ids(list)));
    }
    const items = data.notes.flatMap((note) => note.items);
    expect(new Set(ids(items)).size).toBe(items.length);
    expect(data.next.item).toBeGreaterThan(Math.max(0, ...ids(items)));
  });

  it("have money from the first days of the month before last up to today", () => {
    const data = seed("ru", MORNING);
    const days = data.entries.map((entry) => entry.day).sort();
    expect(days[0]?.slice(0, 7)).toBe("2026-08");
    expect(days.filter((day) => day > "2026-10-07")).toEqual([]);
    expect(days.filter((day) => day >= "2026-10-01").length).toBeGreaterThan(5);
    expect(data.categories).toHaveLength(16);
    expect(data.categories.filter((category) => category.budget !== null).map((category) => category.preset))
      .toEqual(["cafe", "fun"]);
  });

  it("spend about 85 % of the budget in a whole month, warn at 80 % at its end, and earn more than they spend", () => {
    // Two whole months behind each of twelve visits, in both languages: 48 months.
    const found: string[] = [];
    for (const language of ["ru", "en"] as Lang[]) {
      for (let month = 0; month < 12; month += 1) {
        const data = seed(language, Date.UTC(2027, month, 3, 9));
        for (const back of [1, 2]) {
          const key = new Date(Date.UTC(2027, month - back, 1)).toISOString().slice(0, 7);
          const { spent, income, cafe, fun, warned } = monthOf(data, key);
          const last = monthLength(`${key}-01`);
          const share = spent / 30_000;
          if (share < 0.82 || share > 0.88) found.push(`${language} ${key}: ${Math.round(share * 100)} % of the budget`);
          if (income <= spent) found.push(`${language} ${key}: earned ${income}, spent ${spent}`);
          if (cafe >= 3200 || fun >= 2400) found.push(`${language} ${key}: «Кафе» ${cafe}, «Развлечения» ${fun}`);
          if (warned === null || Number(warned.slice(8)) < last - 6) found.push(`${language} ${key}: 80 % on ${warned}`);
        }
      }
    }
    expect(found).toEqual([]);
  });
});
