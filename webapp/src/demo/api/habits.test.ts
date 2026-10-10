import { describe, expect, it } from "vitest";
import type { Habit, HabitDetail, SharedCard } from "../../api/types";
import { demoApi, problem } from "./testApi";

const NO_CONTENT = { status: 204, body: null, headers: {} };

/** A demo whose first habit has the marks given, and began on `created`. */
function withMarks(created: string, marks: [string, boolean][], weeklyGoal = 7) {
  const demo = demoApi();
  const habit = demo.visit.data.habits[0];
  if (!habit) throw new Error("No habit seeded");
  Object.assign(habit, { created_on: created, weekly_goal: weeklyGoal, marks: new Map(marks) });
  return demo;
}

describe("the habits (routers/habits.py, services/habits.py)", () => {
  it("GET /habits: each with its statistics on the user's today", () => {
    const habits = demoApi().read<Habit[]>("GET /habits");
    expect(habits.map((habit) => [habit.name, habit.emoji, habit.color, habit.weekly_goal, habit.streak_unit])).toEqual([
      ["Спорт", "💪", "mint", 7, "days"], ["Читать 20 страниц", "📚", "violet", 7, "days"],
      ["Бассейн", "🏊", "sky", 3, "weeks"], ["Без сахара", "🍎", "amber", 7, "days"],
    ]);
    expect(habits[0]).toMatchObject({ id: 1, created_on: "2025-09-02", day: "2026-10-07", done_today: null, total_days: 401 });
    for (const habit of habits) {
      expect(habit.week).toHaveLength(7);
      expect(habit.last_days).toHaveLength(9);
      expect(habit.percent).toBeGreaterThanOrEqual(0);
      expect(habit.percent).toBeLessThanOrEqual(100);
    }
  });

  it("counts a daily habit as habits.py does: streak, record, percent, week, last days", () => {
    const { read } = withMarks("2026-09-28", [
      ["2026-09-28", true], ["2026-09-29", true], ["2026-09-30", false], ["2026-10-01", true], ["2026-10-02", true],
      ["2026-10-04", true], ["2026-10-05", true], ["2026-10-06", true],
    ]);
    expect(read<Habit[]>("GET /habits")[0]).toEqual({
      id: 1, name: "Спорт", emoji: "💪", color: "mint", weekly_goal: 7, created_on: "2026-09-28", day: "2026-10-07",
      done_today: null, streak: 3, streak_unit: "days", record: 3, percent: 78, week_done: 2, week_goal: 7,
      week: "11-....", done_days: 7, total_days: 10,
      last_days: [true, false, true, true, null, true, true, true, null],
    });
  });

  it("counts a weekly habit by the weeks whose goal was met", () => {
    const { read } = withMarks("2026-09-21", [
      ["2026-09-21", true], ["2026-09-23", true], ["2026-09-25", true],
      ["2026-09-28", true], ["2026-09-29", true],
      ["2026-10-05", true], ["2026-10-06", true], ["2026-10-07", true],
    ], 3);
    expect(read<Habit[]>("GET /habits")[0]).toMatchObject({
      done_today: true, streak: 1, streak_unit: "weeks", record: 1, percent: 67, week_done: 3, week_goal: 3, week: "111....",
    });
  });

  it("GET /habits/{habit_id}: the habit with its year, 53 weeks from a Monday", () => {
    const { read, call } = withMarks("2026-09-28", [["2026-10-05", true], ["2026-10-06", false]]);
    const habit = read<HabitDetail>("GET /habits/1");
    expect(habit.year_from).toBe("2025-10-06");
    expect(habit.year).toHaveLength(371);
    expect(habit.year.slice(-10)).toBe("---10-....");
    expect(habit.year.slice(0, 357)).toBe(".".repeat(357));
    expect(call("GET /habits/9")).toEqual(problem(404, "not_found", { entity: "habit" }));
  });

  it("POST /habits: a new one from today, up to ten, its name its own", () => {
    const { call } = demoApi();
    const created = call("POST /habits", { name: " Йога ", emoji: "🧘", color: "sky", weekly_goal: 3 });
    expect(created.status).toBe(201);
    expect(created.body).toMatchObject({
      id: 5, name: "Йога", emoji: "🧘", color: "sky", weekly_goal: 3, created_on: "2026-10-07", done_today: null,
      streak: 0, record: 0, percent: 0, week_done: 0, week_goal: 3, week: "..-....", done_days: 0, total_days: 1,
    });
    expect(call("POST /habits", { name: "Медитация" }).body).toMatchObject({ emoji: "🎯", color: "mint", weekly_goal: 7 });
    expect(call("POST /habits", { name: "СПОРТ" })).toEqual(problem(422, "validation_error", { field: "name", reason: "duplicate" }));
    expect(call("POST /habits", { name: "  " })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "length", limit: 50 }),
    );
    expect(call("POST /habits", { name: "x".repeat(51) })).toEqual(problem(422, "validation_error", { field: "name", limit: 50 }));
    expect(call("POST /habits", { name: "x", emoji: "🦄" })).toEqual(problem(422, "validation_error", { field: "emoji", reason: "invalid" }));
    expect(call("POST /habits", { name: "x", color: "red" })).toEqual(problem(422, "validation_error", { field: "color", reason: "invalid" }));
    expect(call("POST /habits", { name: "x", weekly_goal: 8 })).toEqual(problem(422, "validation_error", { field: "weekly_goal", limit: 7 }));
    for (const name of ["a", "b", "c", "d"]) expect(call("POST /habits", { name }).status).toBe(201);
    expect(call("POST /habits", { name: "e" })).toEqual(problem(409, "limit_reached", { entity: "habit", limit: 10 }));
  });

  it("PATCH /habits/{habit_id}: its name, look and goal; a new goal recounts the history", () => {
    const { read, call } = demoApi();
    expect(read<Habit>("PATCH /habits/2", { name: "Читать", color: "rose" })).toMatchObject({ id: 2, name: "Читать", color: "rose" });
    expect(read<Habit>("PATCH /habits/2", { weekly_goal: 5 })).toMatchObject({ weekly_goal: 5, streak_unit: "weeks" });
    expect(call("PATCH /habits/2", { name: "Бассейн" })).toEqual(problem(422, "validation_error", { field: "name", reason: "duplicate" }));
    expect(call("PATCH /habits/2", { emoji: "🦄" })).toEqual(problem(422, "validation_error", { field: "emoji", reason: "invalid" }));
    expect(read<Habit>("PATCH /habits/2", { name: "читать" }).name).toBe("читать");
    expect(call("PATCH /habits/9", { name: "x" })).toEqual(problem(404, "not_found", { entity: "habit" }));
  });

  it("DELETE /habits/{habit_id}: gone, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /habits/3")).toEqual(NO_CONTENT);
    expect(read<Habit[]>("GET /habits").map((habit) => habit.id)).toEqual([1, 2, 4]);
    expect(call("DELETE /habits/3")).toEqual(problem(404, "not_found", { entity: "habit" }));
  });

  it("PUT /habits/{habit_id}/marks/{day}: done, missed or no mark, from its first day to today", () => {
    const { read, call } = withMarks("2026-10-01", [["2026-10-05", true], ["2026-10-06", true]]);
    expect(read<Habit>("PUT /habits/1/marks/2026-10-07", { done: true })).toMatchObject({ done_today: true, streak: 3, week: "111...." });
    expect(read<Habit>("PUT /habits/1/marks/2026-10-06", { done: false })).toMatchObject({ streak: 1, week: "101...." });
    expect(read<Habit>("PUT /habits/1/marks/2026-10-07", { done: null })).toMatchObject({ done_today: null, streak: 0 });
    expect(call("PUT /habits/1/marks/2026-09-30", { done: true })).toEqual(
      problem(422, "validation_error", { field: "day", reason: "out_of_range" }),
    );
    expect(call("PUT /habits/1/marks/2026-10-08", { done: true })).toEqual(
      problem(422, "validation_error", { field: "day", reason: "out_of_range" }),
    );
    expect(call("PUT /habits/1/marks/2026-10-32", { done: true })).toEqual(problem(422, "validation_error", { field: "day" }));
    expect(call("PUT /habits/1/marks/2026-10-07", {})).toEqual(problem(422, "validation_error", { field: "done", detail: "Field required" }));
    expect(call("PUT /habits/9/marks/2026-10-07", { done: true })).toEqual(problem(404, "not_found", { entity: "habit" }));
  });
});

describe("a habit's card (routers/habits.py)", () => {
  it("POST /habits/{habit_id}/share: a prepared message of the card", () => {
    const { read, call } = demoApi();
    expect(read<SharedCard>("POST /habits/2/share")).toEqual({ prepared_id: "demo-habit-2-1" });
    expect(read<SharedCard>("POST /habits/2/share")).toEqual({ prepared_id: "demo-habit-2-2" });
    expect(call("POST /habits/9/share")).toEqual(problem(404, "not_found", { entity: "habit" }));
  });

  it("POST /habits/{habit_id}/card: sent to the chat with the bot, if the bot may write", () => {
    const { visit, call } = demoApi();
    expect(call("POST /habits/1/card")).toEqual(NO_CONTENT);
    expect(call("POST /habits/9/card")).toEqual(problem(404, "not_found", { entity: "habit" }));
    visit.data.profile.can_write = false;
    expect(call("POST /habits/1/card")).toEqual(problem(403, "write_forbidden"));
  });
});
