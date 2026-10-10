import { describe, expect, it } from "vitest";
import type { Agenda, ParsedPhrase, Reminder } from "../../api/types";
import { demoApi, MORNING, problem } from "./testApi";
import { HOUR } from "./time";

const NO_CONTENT = { status: 204, body: null, headers: {} };

describe("the reminders (routers/reminders.py, services/reminders.py)", () => {
  it("GET /reminders: the pending ones by their next time, with the repeats described", () => {
    const reminders = demoApi().read<Reminder[]>("GET /reminders");
    expect(reminders.map((reminder) => [reminder.id, reminder.due_local])).toEqual([
      [1, "2026-10-07T12:00"], [2, "2026-10-07T14:30"], [6, "2026-10-08T07:30"], [5, "2026-10-08T08:00"],
      [3, "2026-10-08T10:00"], [7, "2026-10-08T18:00"], [8, "2026-10-10T12:00"], [4, "2026-10-10T19:00"],
    ]);
    expect(reminders[0]).toEqual({
      id: 1, text: "Забрать посылку", due_at: "2026-10-07T09:00:00Z", due_local: "2026-10-07T12:00", status: "pending",
      repeat: "none", rule: null, description: null,
    });
    expect(reminders[2]).toEqual({
      id: 6, text: "Зарядка", due_at: "2026-10-08T04:30:00Z", due_local: "2026-10-08T07:30", status: "pending",
      repeat: "weekly",
      rule: { repeat: "weekly", time_local: "07:30", weekdays: 31, interval_weeks: 1, month_day: null, anchor_date: "2026-09-07" },
      description: "по будням в 07:30",
    });
    expect(reminders.slice(5, 7).map((reminder) => reminder.description)).toEqual([
      "раз в 2 недели: вт, чт в 18:00", "каждый месяц 10-го в 12:00",
    ]);
    expect(demoApi("en").read<Reminder[]>("GET /reminders").map((reminder) => reminder.description).slice(2)).toEqual([
      "on weekdays at 07:30", "every day at 08:00", null, "every other week: Tue, Thu at 18:00", "monthly on day 10 at 12:00", null,
    ]);
  });

  it("GET /reminders: a one-off is gone once its time has come", () => {
    const { read, setNow } = demoApi();
    setNow(MORNING + 2 * HOUR);
    expect(read<Reminder[]>("GET /reminders").map((reminder) => reminder.id)).toEqual([2, 6, 5, 3, 7, 8, 4]);
  });

  it("POST /reminders: once, at a moment ahead", () => {
    const { call } = demoApi();
    expect(call("POST /reminders", { text: " Позвонить маме ", due_local: "2026-10-07T19:00" })).toEqual({
      status: 201,
      body: {
        id: 9, text: "Позвонить маме", due_at: "2026-10-07T16:00:00Z", due_local: "2026-10-07T19:00", status: "pending",
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

  it("POST /reminders: a repeat whose first day is more than a year ahead, as recurrence.local_days walks it", () => {
    // The walk for the next firing starts at the later of the day and the anchor, as on the server.
    const far = demoApi().read<Reminder>("POST /reminders", {
      text: "Продлить визу", rule: { repeat: "weekly", time_local: "18:00", weekdays: 2, interval_weeks: 2, anchor_date: "2027-11-15" },
    });
    expect(far).toMatchObject({ due_local: "2027-11-16T18:00", rule: { anchor_date: "2027-11-16" } });
  });

  it("POST /reminders: up to 20 pending", () => {
    const { call } = demoApi();
    for (let count = 9; count <= 20; count += 1) {
      expect(call("POST /reminders", { text: `${count}`, due_local: "2026-10-09T10:00" }).status).toBe(201);
    }
    expect(call("POST /reminders", { text: "21", due_local: "2026-10-09T10:00" })).toEqual(
      problem(409, "limit_reached", { entity: "reminder", limit: 20 }),
    );
  });

  it("PATCH /reminders/{reminder_id}: the text, the moment or the rule", () => {
    const { read, call } = demoApi();
    expect(read<Reminder>("PATCH /reminders/3", { text: "Сдать лабу" })).toMatchObject({ text: "Сдать лабу", due_local: "2026-10-08T10:00" });
    expect(read<Reminder>("PATCH /reminders/3", { due_local: "2026-10-09T09:00" })).toMatchObject({ due_local: "2026-10-09T09:00" });
    expect(call("PATCH /reminders/3", { due_local: "2026-10-07T09:00" })).toEqual(
      problem(422, "validation_error", { field: "when", reason: "past" }),
    );
    const daily = read<Reminder>("PATCH /reminders/3", { rule: { repeat: "daily", time_local: "21:00" } });
    expect(daily).toMatchObject({ repeat: "daily", due_local: "2026-10-07T21:00", description: "каждый день в 21:00" });
    // The same rule again, as the form sends it with a new text: the series keeps its firings.
    expect(read<Reminder>("PATCH /reminders/5", {
      text: "Пить воду", rule: { repeat: "daily", time_local: "08:00", anchor_date: "2026-10-07" },
    })).toMatchObject({ text: "Пить воду", rule: { anchor_date: "2026-09-07" }, due_local: "2026-10-08T08:00" });
    expect(read<Reminder>("PATCH /reminders/5", { due_local: "2026-10-10T10:00" })).toMatchObject({
      repeat: "none", rule: null, due_local: "2026-10-10T10:00",
    });
    expect(call("PATCH /reminders/3", { due_local: "2026-10-09T09:00", rule: { repeat: "daily", time_local: "21:00" } }))
      .toEqual(problem(422, "validation_error", { field: "due_local", reason: "schedule" }));
    expect(call("PATCH /reminders/99", { text: "a" })).toEqual(problem(404, "not_found", { entity: "reminder" }));
  });

  it("DELETE /reminders/{reminder_id}: cancelled, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /reminders/5")).toEqual(NO_CONTENT);
    expect(read<Reminder[]>("GET /reminders").map((reminder) => reminder.id)).toEqual([1, 2, 6, 3, 7, 8, 4]);
    expect(call("DELETE /reminders/5")).toEqual(problem(404, "not_found", { entity: "reminder" }));
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
      { kind: "reminder", id: 6, time: "07:30", text: "Зарядка", repeat: "weekly", description: "по будням в 07:30" },
      { kind: "reminder", id: 5, time: "08:00", text: "Выпить воды", repeat: "daily", description: "каждый день в 08:00" },
      { kind: "lesson", time: "10:40", end: "12:10", title: "Математический анализ", lesson_kind: "ЛК", room: "А-16" },
      { kind: "reminder", id: 1, time: "12:00", text: "Забрать посылку", repeat: "none", description: null },
      { kind: "lesson", time: "12:40", end: "14:10", title: "Разработка баз данных", lesson_kind: "ПР", room: "И-212-б" },
      { kind: "reminder", id: 2, time: "14:30", text: "Созвон по курсовой", repeat: "none", description: null },
    ]);
    // Every other week on Tuesdays and Thursdays: this week is one of them.
    const plants = (day: number) => agenda.days[day]?.items.filter((item) => item.kind === "reminder" && item.id === 7);
    expect([1, 3].map((day) => plants(day)?.map((item) => item.time))).toEqual([["18:00"], ["18:00"]]);
    expect(agenda.days[6]?.items.map((item) => item.time)).toEqual(["08:00", "12:00"]);
    const later = demoApi().read<Agenda>("GET /agenda?from=2026-10-12&to=2026-10-18");
    expect(later.days.flatMap((day) => day.items).some((item) => item.kind === "reminder" && item.id === 7)).toBe(false);
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
  /** What the form fills in from a phrase: the bot's answer, its defaults left out. */
  const parsed = (text: string, answer: Partial<ParsedPhrase>): ParsedPhrase => ({
    text, repeat: "none", date: null, time: null, weekdays: null, interval_weeks: 1, month_day: null, description: null,
    ...answer,
  });
  /** The answer at the README's moment, Wednesday 7 October 2026, 10:30 in Moscow, in the phrase's language. */
  const parse = (phrase: string) =>
    demoApi(/[а-яё]/i.test(phrase) ? "ru" : "en").call("POST /reminders/parse", { text: phrase });

  it("POST /reminders/parse: the README's three phrases, in Russian and in English", () => {
    const weekdays = { repeat: "weekly", date: "2026-10-08", time: "07:30", weekdays: 31 } as const;
    for (const [phrase, answer] of [
      ["завтра в 9 купить молоко", parsed("купить молоко", { date: "2026-10-08", time: "09:00" })],
      ["через 20 минут чай", parsed("чай", { date: "2026-10-07", time: "10:50" })],
      ["по будням в 7:30 зарядка", parsed("зарядка", { ...weekdays, description: "по будням в 07:30" })],
      ["tomorrow at 9 buy milk", parsed("buy milk", { date: "2026-10-08", time: "09:00" })],
      ["in 20 minutes tea", parsed("tea", { date: "2026-10-07", time: "10:50" })],
      ["on weekdays at 7:30 workout", parsed("workout", { ...weekdays, description: "on weekdays at 07:30" })],
    ] as const) {
      expect(parse(phrase), phrase).toEqual({ status: 200, body: answer, headers: { "Content-Type": "application/json" } });
    }
  });

  it("POST /reminders/parse: the days, the times and the repeats of §5.4, read as the bot reads them", () => {
    // Each answer is the one routers/reminders.py gives with services/phrases.py at the same moment.
    const weekly = (weekdays: number, date: string, time: string, description: string, interval_weeks = 1) =>
      ({ repeat: "weekly", weekdays, date, time, description, interval_weeks }) as const;
    const monthly = { repeat: "monthly", date: "2026-11-05", time: "10:00", month_day: 5 } as const;
    const TABLE: [string, ParsedPhrase][] = [
      // Days, a weekday, a time alone: a time already gone today means tomorrow, a weekday next week.
      ["сегодня в 18 позвонить маме", parsed("позвонить маме", { date: "2026-10-07", time: "18:00" })],
      ["сегодня в 9 позвонить", parsed("позвонить", { date: "2026-10-07", time: "09:00" })],
      ["послезавтра сдать отчёт", parsed("сдать отчёт", { date: "2026-10-09" })],
      ["на завтра в 9 молоко", parsed("молоко", { date: "2026-10-08", time: "09:00" })],
      ["в среду", parsed("", { date: "2026-10-07" })],
      ["в среду в 19 бассейн", parsed("бассейн", { date: "2026-10-07", time: "19:00" })],
      ["в среду в 9:30 созвон", parsed("созвон", { date: "2026-10-14", time: "09:30" })],
      ["в пятницу сдать долг", parsed("сдать долг", { date: "2026-10-09" })],
      ["в следующую пятницу в 10 отчёт", parsed("отчёт", { date: "2026-10-16", time: "10:00" })],
      ["today at 18:00 call mum", parsed("call mum", { date: "2026-10-07", time: "18:00" })],
      ["the day after tomorrow at 9 call", parsed("call", { date: "2026-10-09", time: "09:00" })],
      ["tomorrow buy milk", parsed("buy milk", { date: "2026-10-08" })],
      ["on Wednesday at 9:30 meeting", parsed("meeting", { date: "2026-10-14", time: "09:30" })],
      ["on friday pay back", parsed("pay back", { date: "2026-10-09" })],
      ["wednesday at 7 pm swim", parsed("swim", { date: "2026-10-07", time: "19:00" })],
      ["next friday at 10 report", parsed("report", { date: "2026-10-16", time: "10:00" })],
      ["в 9", parsed("", { date: "2026-10-08", time: "09:00" })],
      ["в 23 спать", parsed("спать", { date: "2026-10-07", time: "23:00" })],
      ["в 9.30 зарядка", parsed("зарядка", { date: "2026-10-08", time: "09:30" })],
      ["в 19.45 позвонить", parsed("позвонить", { date: "2026-10-07", time: "19:45" })],
      ["19:45 позвонить", parsed("позвонить", { date: "2026-10-07", time: "19:45" })],
      ["в 9 часов зарядка", parsed("зарядка", { date: "2026-10-08", time: "09:00" })],
      ["к 9 на работу", parsed("на работу", { date: "2026-10-08", time: "09:00" })],
      ["в 8 вечера кино", parsed("кино", { date: "2026-10-07", time: "20:00" })],
      ["утром в 7 пробежка", parsed("пробежка", { date: "2026-10-08", time: "07:00" })],
      ["в 12 ночи спать", parsed("спать", { date: "2026-10-08", time: "00:00" })],
      ["в полдень обед", parsed("обед", { date: "2026-10-07", time: "12:00" })],
      ["at 9:30 standup", parsed("standup", { date: "2026-10-08", time: "09:30" })],
      ["at 7:30 am run", parsed("run", { date: "2026-10-08", time: "07:30" })],
      ["7pm dinner", parsed("dinner", { date: "2026-10-07", time: "19:00" })],
      ["at midnight sleep", parsed("sleep", { date: "2026-10-08", time: "00:00" })],
      ["в 9 купить 3 яблока", parsed("купить 3 яблока", { date: "2026-10-08", time: "09:00" })],
      ["завтра купить 2 батона", parsed("купить 2 батона", { date: "2026-10-08" })],
      // A time ahead: minutes and hours an exact moment, days and weeks a day.
      ["через 2 часа выключить духовку", parsed("выключить духовку", { date: "2026-10-07", time: "12:30" })],
      ["через час позвонить", parsed("позвонить", { date: "2026-10-07", time: "11:30" })],
      ["через пять минут чай", parsed("чай", { date: "2026-10-07", time: "10:35" })],
      ["через полчаса выйти", parsed("выйти", { date: "2026-10-07", time: "11:00" })],
      ["через 1 час 30 минут созвон", parsed("созвон", { date: "2026-10-07", time: "12:00" })],
      ["через 3 дня в 10 позвонить", parsed("позвонить", { date: "2026-10-10", time: "10:00" })],
      ["через неделю отчёт", parsed("отчёт", { date: "2026-10-14" })],
      ["in 2 hours turn off the oven", parsed("turn off the oven", { date: "2026-10-07", time: "12:30" })],
      ["in an hour call", parsed("call", { date: "2026-10-07", time: "11:30" })],
      ["in 2 hours and 15 minutes call", parsed("call", { date: "2026-10-07", time: "12:45" })],
      ["in 2 weeks at 9 dentist", parsed("dentist", { date: "2026-10-21", time: "09:00" })],
      // Repeats, from their first firing on.
      ["каждый день в 8 выпить воды", parsed("выпить воды", { repeat: "daily", date: "2026-10-08", time: "08:00", description: "каждый день в 08:00" })],
      ["каждый день зарядка", parsed("зарядка", { repeat: "daily" })],
      ["по выходным в 11 пробежка", parsed("пробежка", weekly(96, "2026-10-10", "11:00", "по выходным в 11:00"))],
      ["по средам в 19 бассейн", parsed("бассейн", weekly(4, "2026-10-07", "19:00", "ср в 19:00"))],
      ["по средам бассейн", parsed("бассейн", { repeat: "weekly", weekdays: 4 })],
      ["по вторникам и четвергам в 18:00 полить цветы", parsed("полить цветы", weekly(10, "2026-10-08", "18:00", "вт, чт в 18:00"))],
      ["каждый понедельник в 10 планёрка", parsed("планёрка", weekly(1, "2026-10-12", "10:00", "пн в 10:00"))],
      ["раз в две недели в 18 полить цветы", parsed("полить цветы", weekly(4, "2026-10-07", "18:00", "раз в 2 недели: ср в 18:00", 2))],
      [
        "раз в две недели по вторникам и четвергам в 18:00 полить цветы",
        parsed("полить цветы", weekly(10, "2026-10-08", "18:00", "раз в 2 недели: вт, чт в 18:00", 2)),
      ],
      ["каждую вторую среду в 10 отчёт", parsed("отчёт", weekly(4, "2026-10-14", "10:00", "раз в 2 недели: ср в 10:00", 2))],
      ["каждый месяц 10-го в 12 оплатить телефон", parsed("оплатить телефон", {
        repeat: "monthly", date: "2026-10-10", time: "12:00", month_day: 10, description: "каждый месяц 10-го в 12:00",
      })],
      ["ежемесячно 5-го в 10 аренда", parsed("аренда", { ...monthly, description: "каждый месяц 5-го в 10:00" })],
      ["every day at 8 drink water", parsed("drink water", { repeat: "daily", date: "2026-10-08", time: "08:00", description: "every day at 08:00" })],
      ["on weekends at 11 run", parsed("run", weekly(96, "2026-10-10", "11:00", "on weekends at 11:00"))],
      ["every Monday at 10 meeting", parsed("meeting", weekly(1, "2026-10-12", "10:00", "Mon at 10:00"))],
      ["every monday and wednesday at 8 gym", parsed("gym", weekly(5, "2026-10-12", "08:00", "Mon, Wed at 08:00"))],
      ["every other monday at 10 call", parsed("call", weekly(1, "2026-10-12", "10:00", "every other week: Mon at 10:00", 2))],
      ["monthly on the 5th at 10 rent", parsed("rent", { ...monthly, description: "monthly on day 5 at 10:00" })],
      // «Напомни» and “remind me … to” are not the text, nor are the commas and the full stop around it.
      ["пожалуйста, напомни мне завтра в 9 купить молоко", parsed("купить молоко", { date: "2026-10-08", time: "09:00" })],
      ["remind me tomorrow at 9 to buy milk", parsed("buy milk", { date: "2026-10-08", time: "09:00" })],
      ["завтра в 9, купить молоко.", parsed("купить молоко", { date: "2026-10-08", time: "09:00" })],
      ["Завтра В 9 Купить Молоко", parsed("Купить Молоко", { date: "2026-10-08", time: "09:00" })],
    ];
    const found = TABLE.flatMap(([phrase, answer]) => {
      const reply = parse(phrase);
      return reply.status === 200 && JSON.stringify(reply.body) === JSON.stringify(answer)
        ? [] : [`${phrase}: ${reply.status} ${JSON.stringify(reply.body)}`];
    });
    expect(found).toEqual([]);
  });

  it("POST /reminders/parse: what it does not understand is refused, and the form keeps its fields", () => {
    // No time, day or repeat in it; a time the clock has not; or a date, which the demo leaves to the bot.
    for (const phrase of [
      "купить молоко", "buy milk", "9.30 зарядка", "в 25 часов", "в 2 раза больше", "каждый месяц 32-го в 9 отчёт",
      "25 октября в 10 купить подарок", "10.12 сдать отчёт", "25.10.2026 отчёт", "on October 25 at 10 buy a gift",
      "October 25 buy a gift",
    ]) {
      expect(parse(phrase), phrase).toEqual(problem(422, "validation_error", { field: "text", reason: "phrase_not_understood" }));
    }
    expect(parse(`завтра ${"я".repeat(201)}`)).toEqual(
      problem(422, "validation_error", { field: "text", reason: "length", limit: 200 }),
    );
  });
});
