import { describe, expect, it } from "vitest";
import type { Agenda, ParsedPhrase, Reminder } from "../../api/types";
import { demoApi, MORNING, problem } from "./testApi";
import { HOUR } from "./time";

const NO_CONTENT = { status: 204, body: null, headers: {} };

describe("the reminders (routers/reminders.py, services/reminders.py)", () => {
  it("GET /reminders: the pending ones by their next time, with the repeats described", () => {
    const reminders = demoApi().read<Reminder[]>("GET /reminders");
    expect(reminders.map((reminder) => [reminder.id, reminder.due_local])).toEqual([
      [1, "2026-10-07T12:00"], [4, "2026-10-08T07:30"], [3, "2026-10-08T08:00"], [2, "2026-10-08T10:00"],
    ]);
    expect(reminders[0]).toEqual({
      id: 1, text: "Забрать посылку", due_at: "2026-10-07T09:00:00Z", due_local: "2026-10-07T12:00", status: "pending",
      repeat: "none", rule: null, description: null,
    });
    expect(reminders[1]).toEqual({
      id: 4, text: "Зарядка", due_at: "2026-10-08T04:30:00Z", due_local: "2026-10-08T07:30", status: "pending",
      repeat: "weekly",
      rule: { repeat: "weekly", time_local: "07:30", weekdays: 31, interval_weeks: 1, month_day: null, anchor_date: "2026-09-07" },
      description: "по будням в 07:30",
    });
    expect(demoApi("en").read<Reminder[]>("GET /reminders")[2]?.description).toBe("every day at 08:00");
  });

  it("GET /reminders: a one-off is gone once its time has come", () => {
    const { read, setNow } = demoApi();
    setNow(MORNING + 2 * HOUR);
    expect(read<Reminder[]>("GET /reminders").map((reminder) => reminder.id)).toEqual([4, 3, 2]);
  });

  it("POST /reminders: once, at a moment ahead", () => {
    const { call } = demoApi();
    expect(call("POST /reminders", { text: " Позвонить маме ", due_local: "2026-10-07T19:00" })).toEqual({
      status: 201,
      body: {
        id: 5, text: "Позвонить маме", due_at: "2026-10-07T16:00:00Z", due_local: "2026-10-07T19:00", status: "pending",
        repeat: "none", rule: null, description: null,
      },
      headers: { "Content-Type": "application/json" },
    });
    expect(call("POST /reminders", { text: "a", due_local: "2026-10-07T10:00" })).toEqual(
      problem(422, "validation_error", { field: "when", reason: "past" }),
    );
    expect(call("POST /reminders", { text: "a", due_local: "2026-02-30T10:00" })).toEqual(
      problem(422, "validation_error", { field: "due_local", reason: "format" }),
    );
    expect(call("POST /reminders", { text: "a", due_local: "2026-10-07 19:00" })).toEqual(
      problem(422, "validation_error", { field: "due_local" }),
    );
    expect(call("POST /reminders", { text: "a" })).toEqual(problem(422, "validation_error", { field: "due_local", reason: "schedule" }));
    expect(call("POST /reminders", { text: " ", due_local: "2026-10-07T19:00" })).toEqual(
      problem(422, "validation_error", { field: "text", reason: "length", limit: 200 }),
    );
    expect(call("POST /reminders", { text: "я".repeat(201), due_local: "2026-10-07T19:00" })).toEqual(
      problem(422, "validation_error", { field: "text", reason: "length", limit: 200 }),
    );
  });

  it("POST /reminders: a repeat, from its first firing on; every other week counts from it", () => {
    const { read, call } = demoApi();
    const created = read<Reminder>("POST /reminders", {
      text: "Полить цветы", rule: { repeat: "weekly", time_local: "18:00", weekdays: 2 | 8, interval_weeks: 2 },
    });
    expect(created).toMatchObject({
      due_local: "2026-10-08T18:00", repeat: "weekly", description: "раз в 2 недели: вт, чт в 18:00",
      rule: { repeat: "weekly", time_local: "18:00", weekdays: 10, interval_weeks: 2, month_day: null, anchor_date: "2026-10-08" },
    });
    const monthly = read<Reminder>("POST /reminders", { text: "Оплатить телефон", rule: { repeat: "monthly", time_local: "12:00", month_day: 31 } });
    expect(monthly).toMatchObject({ due_local: "2026-10-31T12:00", description: "каждый месяц 31-го в 12:00" });
    const weekdays = read<Reminder>("POST /reminders", {
      text: "Зарядка", rule: { repeat: "weekly", time_local: "07:00", weekdays: 31, month_day: 5 },
    });
    expect(weekdays.rule).toMatchObject({ weekdays: 31, interval_weeks: 1, month_day: null });
    expect(call("POST /reminders", { text: "a", rule: { repeat: "weekly", time_local: "07:00" } })).toEqual(
      problem(422, "validation_error", { field: "repeat", reason: "repeat_invalid" }),
    );
    expect(call("POST /reminders", { text: "a", rule: { repeat: "daily", time_local: "25:00" } })).toEqual(
      problem(422, "validation_error", { field: "repeat", reason: "repeat_invalid" }),
    );
    expect(call("POST /reminders", { text: "a", rule: { repeat: "daily", time_local: "08:00", anchor_date: "1999-01-01" } })).toEqual(
      problem(422, "validation_error", { field: "rule", reason: "repeat_invalid" }),
    );
    expect(call("POST /reminders", { text: "a", due_local: "2026-10-09T10:00", rule: { repeat: "daily", time_local: "08:00" } }))
      .toEqual(problem(422, "validation_error", { field: "due_local", reason: "schedule" }));
  });

  it("POST /reminders: up to 20 pending", () => {
    const { call } = demoApi();
    for (let count = 5; count <= 20; count += 1) {
      expect(call("POST /reminders", { text: `${count}`, due_local: "2026-10-09T10:00" }).status).toBe(201);
    }
    expect(call("POST /reminders", { text: "21", due_local: "2026-10-09T10:00" })).toEqual(
      problem(409, "limit_reached", { entity: "reminder", limit: 20 }),
    );
  });

  it("PATCH /reminders/{reminder_id}: the text, the moment or the rule", () => {
    const { read, call } = demoApi();
    expect(read<Reminder>("PATCH /reminders/2", { text: "Сдать лабу" })).toMatchObject({ text: "Сдать лабу", due_local: "2026-10-08T10:00" });
    expect(read<Reminder>("PATCH /reminders/2", { due_local: "2026-10-09T09:00" })).toMatchObject({ due_local: "2026-10-09T09:00" });
    expect(call("PATCH /reminders/2", { due_local: "2026-10-07T09:00" })).toEqual(
      problem(422, "validation_error", { field: "when", reason: "past" }),
    );
    const daily = read<Reminder>("PATCH /reminders/2", { rule: { repeat: "daily", time_local: "21:00" } });
    expect(daily).toMatchObject({ repeat: "daily", due_local: "2026-10-07T21:00", description: "каждый день в 21:00" });
    // The same rule again, as the form sends it with a new text: the series keeps its firings.
    expect(read<Reminder>("PATCH /reminders/3", {
      text: "Пить воду", rule: { repeat: "daily", time_local: "08:00", anchor_date: "2026-10-07" },
    })).toMatchObject({ text: "Пить воду", rule: { anchor_date: "2026-09-07" }, due_local: "2026-10-08T08:00" });
    expect(read<Reminder>("PATCH /reminders/3", { due_local: "2026-10-10T10:00" })).toMatchObject({
      repeat: "none", rule: null, due_local: "2026-10-10T10:00",
    });
    expect(call("PATCH /reminders/2", { due_local: "2026-10-09T09:00", rule: { repeat: "daily", time_local: "21:00" } }))
      .toEqual(problem(422, "validation_error", { field: "due_local", reason: "schedule" }));
    expect(call("PATCH /reminders/99", { text: "a" })).toEqual(problem(404, "not_found", { entity: "reminder" }));
  });

  it("DELETE /reminders/{reminder_id}: cancelled, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /reminders/3")).toEqual(NO_CONTENT);
    expect(read<Reminder[]>("GET /reminders").map((reminder) => reminder.id)).toEqual([1, 4, 2]);
    expect(call("DELETE /reminders/3")).toEqual(problem(404, "not_found", { entity: "reminder" }));
  });
});

describe("the calendar (routers/agenda.py)", () => {
  it("GET /agenda: every day of the range with its reminders, lessons and week label", () => {
    const agenda = demoApi().read<Agenda>("GET /agenda?from=2026-10-05&to=2026-10-11");
    expect(agenda.days.map((day) => day.date)).toEqual([
      "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11",
    ]);
    expect(agenda.days.every((day) => day.label === "6 неделя")).toBe(true);
    expect(agenda.days[2]?.items).toEqual([
      { kind: "reminder", id: 4, time: "07:30", text: "Зарядка", repeat: "weekly", description: "по будням в 07:30" },
      { kind: "reminder", id: 3, time: "08:00", text: "Выпить воды", repeat: "daily", description: "каждый день в 08:00" },
      { kind: "lesson", time: "10:40", end: "12:10", title: "Математический анализ", lesson_kind: "ЛК", room: "А-16" },
      { kind: "reminder", id: 1, time: "12:00", text: "Забрать посылку", repeat: "none", description: null },
      { kind: "lesson", time: "12:40", end: "14:10", title: "Разработка баз данных", lesson_kind: "ПР", room: "И-212-б" },
    ]);
    expect(agenda.days[6]?.items.map((item) => item.time)).toEqual(["08:00", "12:00"]);
  });

  it("GET /agenda: a range of up to 62 days, from a day to a later one", () => {
    const { call } = demoApi();
    expect(call("GET /agenda?from=2026-10-01&to=2026-12-01").status).toBe(200);
    expect(call("GET /agenda?from=2026-10-01&to=2026-12-02")).toEqual(problem(422, "validation_error", { field: "to", reason: "range" }));
    expect(call("GET /agenda?from=2026-10-08&to=2026-10-07")).toEqual(problem(422, "validation_error", { field: "to", reason: "range" }));
    expect(call("GET /agenda?from=2026-10-08")).toEqual(problem(422, "validation_error", { field: "to", detail: "Field required" }));
    expect(call("GET /agenda?from=2026-10-32&to=2026-11-01")).toEqual(problem(422, "validation_error", { field: "from" }));
  });
});

describe("a phrase (routers/reminders.py, services/phrases.py)", () => {
  it("POST /reminders/parse: the day, the time and the repeat it names, the rest as the text", () => {
    const { read } = demoApi();
    expect(read<ParsedPhrase>("POST /reminders/parse", { text: "завтра в 9:30 купить молоко" })).toEqual({
      text: "купить молоко", repeat: "none", date: "2026-10-08", time: "09:30", weekdays: null, interval_weeks: 1,
      month_day: null, description: null,
    });
    expect(read<ParsedPhrase>("POST /reminders/parse", { text: "каждый день в 8:00 зарядка" })).toEqual({
      text: "зарядка", repeat: "daily", date: "2026-10-08", time: "08:00", weekdays: null, interval_weeks: 1,
      month_day: null, description: "каждый день в 08:00",
    });
    expect(read<ParsedPhrase>("POST /reminders/parse", { text: "19.45 позвонить" })).toMatchObject({
      text: "позвонить", date: "2026-10-07", time: "19:45",
    });
    expect(read<ParsedPhrase>("POST /reminders/parse", { text: "послезавтра сдать отчёт" })).toMatchObject({
      text: "сдать отчёт", date: "2026-10-09", time: null,
    });
    expect(demoApi("en").read<ParsedPhrase>("POST /reminders/parse", { text: "tomorrow at 9:30 buy milk" })).toMatchObject({
      text: "buy milk", date: "2026-10-08", time: "09:30",
    });
  });

  it("POST /reminders/parse: what it does not understand is refused, and the form keeps its fields", () => {
    const { call } = demoApi();
    expect(call("POST /reminders/parse", { text: "купить молоко" })).toEqual(
      problem(422, "validation_error", { field: "text", reason: "phrase_not_understood" }),
    );
    expect(call("POST /reminders/parse", { text: `завтра ${"я".repeat(201)}` })).toEqual(
      problem(422, "validation_error", { field: "text", reason: "length", limit: 200 }),
    );
  });
});
