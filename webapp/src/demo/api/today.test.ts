import { describe, expect, it } from "vitest";
import type { Habit, MoneyMonth, Note, Today } from "../../api/types";
import { demoApi, MORNING } from "./testApi";
import { HOUR } from "./time";

describe("«Сегодня» (routers/today.py, services/digest.py)", () => {
  it("GET /today: the day on the user's clock, with all its parts", () => {
    const today = demoApi().read<Today>("GET /today");
    expect(today).toMatchObject({
      date: "2026-10-07",
      part_of_day: "morning",
      weather: {
        city: "Москва", temperature: expect.any(Number), feels_like: expect.any(Number), wind: expect.any(Number),
        code: expect.any(Number), emoji: expect.any(String), description: expect.any(String),
        tmin: expect.any(Number), tmax: expect.any(Number), tips: expect.any(Array),
      },
      reminders_today: [
        { id: 1, text: "Забрать посылку", time: "12:00", due_at: "2026-10-07T09:00:00Z" },
        { id: 2, text: "Созвон по курсовой", time: "14:30", due_at: "2026-10-07T11:30:00Z" },
      ],
      habits: { done: 1, total: 4 },
      notes_count: 8,
      rates: { date: "2026-10-07", usd: { value: expect.any(Number), change: expect.any(Number) } },
      has_schedule: true,
      week_label: "6 неделя",
      tomorrow: null,
      classes_weather: {
        start: "10:40", start_temp: expect.any(Number), end: "14:10", end_temp: expect.any(Number),
      },
      pinned_notes: [
        { id: 1, text: "Покупки", done: 3, total: 7 },
        { id: 2, text: "Собрать в поездку", done: 4, total: 8 },
        { id: 3, text: "Код домофона: 45В7", done: 0, total: 0 },
      ],
    });
    expect(today.lessons).toEqual([
      {
        time: "10:40", end: "12:10", title: "Математический анализ", kind: "ЛК", room: "А-16",
        starts_at: "2026-10-07T07:40:00Z", ends_at: "2026-10-07T09:10:00Z",
      },
      {
        time: "12:40", end: "14:10", title: "Разработка баз данных", kind: "ПР", room: "И-212-б",
        starts_at: "2026-10-07T09:40:00Z", ends_at: "2026-10-07T11:10:00Z",
      },
    ]);
  });

  it("agrees with the screens it sums up: habits, notes and money", () => {
    const { read } = demoApi();
    const today = read<Today>("GET /today");
    expect(today.habits.items).toEqual(read<Habit[]>("GET /habits"));
    expect(today.notes_count).toBe(read<Note[]>("GET /notes").length);
    const month = read<MoneyMonth>("GET /money");
    expect(today.money).toEqual({
      currency: "RUB", today: month.days[6], spent: month.spent, budget: 3_000_000, left: month.left,
      per_day: month.per_day, count: month.entries.length,
    });
    const worth = (habit: Habit) => habit.streak * (habit.streak_unit === "days" ? 1 : 7);
    const best = today.habits.items
      .filter((habit) => habit.streak > 0)
      .reduce<Habit | null>((top, habit) => (top === null || worth(habit) > worth(top) ? habit : top), null);
    expect(today.best_streak).toEqual(best && { name: best.name, count: best.streak, unit: best.streak_unit });
  });

  it("tells tomorrow's weather from 17:00, and the part of the day by the hour", () => {
    const { read, setNow } = demoApi();
    setNow(MORNING + 8 * HOUR); // 18:30
    const evening = read<Today>("GET /today");
    expect(evening.part_of_day).toBe("evening");
    expect(evening.tomorrow?.date).toBe("2026-10-08");
    setNow(MORNING + 14 * HOUR); // 00:30 on Thursday
    const night = read<Today>("GET /today");
    expect(night).toMatchObject({ date: "2026-10-08", part_of_day: "night" });
    expect(night.reminders_today.map((reminder) => [reminder.time, reminder.text])).toEqual([
      ["07:30", "Зарядка"], ["08:00", "Выпить воды"], ["10:00", "Сдать лабораторную"], ["18:00", "Полить цветы"],
    ]);
    expect(night.lessons.map((lesson) => lesson.title)).toEqual(["Физика", "Разработка баз данных"]);
  });

  it("has no lessons without a timetable", () => {
    const { read, call } = demoApi();
    call("DELETE /schedule");
    expect(read<Today>("GET /today")).toMatchObject({
      has_schedule: false, lessons: [], week_label: null, classes_weather: null,
    });
  });
});
