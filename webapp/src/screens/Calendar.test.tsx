import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { keys } from "../api/queries";
import type { AgendaItem, LessonItem, ReminderItem } from "../api/types";
import { addDaysIso, weekOf } from "../lib/format";
import { installTelegram } from "../test/fakeTelegram";
import { me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { RATE_LIMITED, refresh } from "../test/refresh";
import { renderWithApp } from "../test/render";
import { CalendarScreen } from "./Calendar";

function item(id: number, time: string, text: string, extra: Partial<ReminderItem> = {}): ReminderItem {
  return { kind: "reminder", id, time, text, repeat: "none", description: null, ...extra };
}

function lesson(time: string, end: string, title: string, extra: Partial<LessonItem> = {}): LessonItem {
  return { kind: "lesson", time, end, title, lesson_kind: null, room: null, ...extra };
}

function week(monday: string, items: Record<string, AgendaItem[]> = {}, label: string | null = null) {
  return { days: weekOf(monday).map((date) => ({ date, label, items: items[date] ?? [] })) };
}

/** Every day between `fromIso` and `toIso` inclusive — for mocking a month-sized agenda range. */
function range(fromIso: string, toIso: string, items: Record<string, AgendaItem[]> = {}) {
  const days: { date: string; label: string | null; items: AgendaItem[] }[] = [];
  for (let iso = fromIso; iso <= toIso; iso = addDaysIso(iso, 1)) {
    days.push({ date: iso, label: null, items: items[iso] ?? [] });
  }
  return { days };
}

const PILLS = item(2, "21:00", "Таблетки", { repeat: "daily", description: "каждый день в 21:00" });

function at(iso: string) {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(iso));
}

afterEach(() => vi.useRealTimers());

describe("Calendar", () => {
  it("opens on today with its items", async () => {
    at("2026-09-29T09:00:00Z"); // Tuesday, 12:00 in Moscow
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", {
        "2026-09-29": [item(1, "10:40", "Пара"), PILLS],
      }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByRole("heading", { level: 2 })).toHaveTextContent(
      "Сегодня · вторник, 29 сентября",
    );
    expect(await screen.findByText("2 напоминания")).toBeInTheDocument();
    expect(screen.getByText("↻ Таблетки")).toBeInTheDocument();
    expect(screen.getByText("каждый день в 21:00")).toBeInTheDocument();
    const todayCell = screen.getByRole("button", { name: "Сегодня · вторник, 29 сентября" });
    expect(todayCell).toHaveAttribute("aria-current", "date");
    expect(todayCell).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "↩ Сегодня" })).not.toBeInTheDocument();
  });

  it("selects another day and comes back to today", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({ "GET /me": me, "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28") });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Послезавтра · четверг, 1 октября" }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Послезавтра · четверг, 1 октября");
    expect(screen.getByText("Ничего не запланировано")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "↩ Сегодня" }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Сегодня · вторник, 29 сентября");
  });

  it("moves between weeks", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
      "GET /agenda?from=2026-10-05&to=2026-10-11": week("2026-10-05", {
        "2026-10-06": [item(3, "09:00", "Врач")],
      }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Следующая неделя" }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Вторник, 6 октября");
    expect(await screen.findByText("Врач")).toBeInTheDocument();
    expect(screen.getByText("5 окт. – 11 окт.")).toBeInTheDocument();
  });

  it("uses the city's day, not the device's", async () => {
    at("2026-09-28T20:00:00Z"); // already 29 September in Vladivostok
    installTelegram();
    mockApi({
      "GET /me": { ...me, city: { ...me.city, name: "Владивосток", timezone: "Asia/Vladivostok" } },
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Сегодня · вторник, 29 сентября"),
    );
  });

  it("titles the screen and names all seven weekdays in the month", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
      "GET /agenda?from=2026-08-31&to=2026-10-04": { days: [] },
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByRole("heading", { level: 1, name: /Календарь/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Календарь Показать месяц" }));
    for (const name of ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("unfolds the month and picks a day from it", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
      "GET /agenda?from=2026-08-31&to=2026-10-04": { days: [] },
      "GET /agenda?from=2026-09-14&to=2026-09-20": week("2026-09-14"),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Календарь Показать месяц" }));
    expect(screen.getByText("Сентябрь 2026")).toBeInTheDocument();
    expect(screen.getByText("пн")).toBeInTheDocument(); // the weekday column headers
    const day15 = await screen.findByRole("button", {
      name: "Вторник, 15 сентября, Ничего не запланировано",
    });
    fireEvent.click(day15);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Вторник, 15 сентября");
    expect(screen.queryByText("Сентябрь 2026")).not.toBeInTheDocument();
  });

  it("shows a picked day's items at once from the month's cache, then returns to today's week", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    const doctor = item(3, "09:00", "Врач");
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
      "GET /agenda?from=2026-08-31&to=2026-10-04": range("2026-08-31", "2026-10-04", {
        "2026-09-08": [doctor],
      }),
      "GET /agenda?from=2026-09-07&to=2026-09-13": week("2026-09-07", { "2026-09-08": [doctor] }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Календарь Показать месяц" }));
    const sep8 = await screen.findByRole("button", { name: "Вторник, 8 сентября, 1 напоминание" });
    fireEvent.click(sep8);
    // Straight from the month's cache, with no loader in between.
    expect(screen.getByText("Врач")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "↩ Сегодня" }));
    expect(await screen.findByRole("heading", { level: 2 })).toHaveTextContent(
      "Сегодня · вторник, 29 сентября",
    );
  });

  it("asks about the whole series before deleting a repeat", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", { "2026-09-29": [PILLS] }),
      "DELETE /reminders/2": () => ({ status: 204 }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить напоминание" }));
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить повтор «Таблетки» целиком?", expect.any(Function));
    await waitFor(() => expect(calls).toContainEqual({ method: "DELETE", path: "/reminders/2", body: undefined }));
  });

  it("asks about a repeat with a very long text too, quoting its start", async () => {
    at("2026-09-29T09:00:00Z");
    // As telegram-web-app.js: a popup's message over 256 UTF-16 units is refused.
    const showConfirm = vi.fn((message: string, callback: (ok: boolean) => void) => {
      if (message.trim().length > 256) throw new Error("WebAppPopupParamInvalid");
      callback(true);
    });
    installTelegram({ showConfirm });
    const { calls } = mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", {
        "2026-09-29": [{ ...PILLS, text: "а".repeat(300) }],
      }),
      "DELETE /reminders/2": () => ({ status: 204 }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить напоминание" }));
    expect(showConfirm).toHaveBeenCalledWith(`Удалить повтор «${"а".repeat(59)}…» целиком?`, expect.any(Function));
    await waitFor(() => expect(calls).toContainEqual({ method: "DELETE", path: "/reminders/2", body: undefined }));
  });

  it("deletes a one-off reminder after a plain confirmation", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    let items = [item(1, "10:40", "Пара")];
    const { calls } = mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": () => ({
        body: week("2026-09-28", { "2026-09-29": items }),
      }),
      "DELETE /reminders/1": () => {
        items = [];
        return { status: 204 };
      },
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить напоминание" }));
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить напоминание?", expect.any(Function));
    await waitFor(() => expect(screen.queryByText("Пара")).not.toBeInTheDocument());
    expect(calls).toContainEqual({ method: "DELETE", path: "/reminders/1", body: undefined });
  });

  it("shows the loader alone while the week is still loading", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": () => new Promise(() => {}), // never resolves
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Ничего не запланировано")).not.toBeInTheDocument();
    expect(screen.queryByText(/напоминани/)).not.toBeInTheDocument();
  });

  it("shows the error state alone when the week fails to load", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": {
        status: 500,
        body: { status: 500, code: "generic", title: "Oops" },
      },
    });
    const { client } = renderWithApp(<CalendarScreen />, { path: "/calendar" });
    client.setQueryDefaults(["agenda"], { retry: false }); // the app retries a 5xx twice first
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Ничего не запланировано")).not.toBeInTheDocument();
  });

  it("keeps the day on screen when a refresh of the week or of the user fails", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    const days = week("2026-09-28", { "2026-09-29": [item(3, "09:00", "Врач")] });
    mockApi({ "GET /me": me, "GET /agenda?from=2026-09-28&to=2026-10-04": days });
    const { client } = renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByText("Врач")).toBeInTheDocument();
    expect(screen.getByText("1 напоминание")).toBeInTheDocument();

    mockApi({ "GET /me": me, "GET /agenda?from=2026-09-28&to=2026-10-04": RATE_LIMITED });
    await refresh(client, ["agenda"]);
    expect(screen.getByText("Врач")).toBeInTheDocument();
    expect(screen.getByText("1 напоминание")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    mockApi({ "GET /me": RATE_LIMITED, "GET /agenda?from=2026-09-28&to=2026-10-04": days });
    await refresh(client, keys.me);
    expect(screen.getByRole("heading", { level: 1, name: /Календарь/ })).toBeInTheDocument();
    expect(screen.getByText("Врач")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a mostly vertical drag but moves the week on a horizontal one", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28"),
      "GET /agenda?from=2026-10-05&to=2026-10-11": week("2026-10-05"),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    const today = await screen.findByRole("button", { name: "Сегодня · вторник, 29 сентября" });
    const strip = today.closest(".cal-strip");
    if (!strip) throw new Error("strip not found");
    fireEvent.touchStart(strip, { touches: [{ clientX: 200, clientY: 200 }] });
    fireEvent.touchEnd(strip, { changedTouches: [{ clientX: 260, clientY: 320 }] }); // dx 60, dy 120
    expect(screen.getByText("28 сент. – 4 окт.")).toBeInTheDocument();
    fireEvent.touchStart(strip, { touches: [{ clientX: 200, clientY: 200 }] });
    fireEvent.touchEnd(strip, { changedTouches: [{ clientX: 120, clientY: 210 }] }); // dx -80, dy 10
    expect(screen.getByText("5 окт. – 11 окт.")).toBeInTheDocument();
  });

  it("opens an item for editing", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", { "2026-09-29": [PILLS] }),
    });
    const { history } = renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByText("↻ Таблетки"));
    expect(history.at(-1)).toBe("/calendar/2");
  });
});

describe("Calendar lessons", () => {
  const DATABASES = lesson("12:40", "14:10", "Разработка баз данных", { lesson_kind: "ПР", room: "И-212-б" });
  const LECTURE = lesson("09:00", "10:30", "Мобильные приложения", { lesson_kind: "ЛК" });

  it("shows lessons among the reminders, with the week's label and both counts", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week(
        "2026-09-28",
        { "2026-09-29": [LECTURE, PILLS, DATABASES].sort((a, b) => a.time.localeCompare(b.time)) },
        "5 неделя",
      ),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByText("2 пары · 1 напоминание")).toBeInTheDocument();
    expect(screen.getByText("5 неделя · 28 сент. – 4 окт.")).toBeInTheDocument();
    expect(screen.getByText("Разработка баз данных")).toBeInTheDocument();
    expect(screen.getByText("ПР · 12:40–14:10 · И-212-б")).toBeInTheDocument();
    expect(screen.getByText("ЛК · 09:00–10:30")).toBeInTheDocument();
    // Lessons come from the timetable: no link to edit them and nothing to delete.
    expect(screen.getAllByRole("button", { name: "Удалить напоминание" })).toHaveLength(1);
    expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/calendar/2",
      "/calendar/new/2026-09-29",
    ]);
    const today = screen.getByRole("button", { name: "Сегодня · вторник, 29 сентября" });
    expect(today.querySelectorAll(".cal-dot--lesson")).toHaveLength(2);
    expect(today.querySelectorAll(".cal-dot:not(.cal-dot--lesson)")).toHaveLength(1);
  });

  it("counts lessons alone and names them in the month", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", { "2026-09-30": [DATABASES] }),
      "GET /agenda?from=2026-08-31&to=2026-10-04": range("2026-08-31", "2026-10-04", {
        "2026-09-30": [DATABASES],
      }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Завтра · среда, 30 сентября" }));
    expect(screen.getByText("1 пара")).toBeInTheDocument();
    expect(screen.getByText("28 сент. – 4 окт.")).toBeInTheDocument(); // no label, no «·»
    fireEvent.click(screen.getByRole("button", { name: "Календарь Показать месяц" }));
    expect(await screen.findByRole("button", { name: "Завтра · среда, 30 сентября, 1 пара" })).toBeInTheDocument();
  });

  it("counts in English", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", {
        "2026-09-29": [LECTURE, DATABASES, PILLS],
        "2026-09-30": [DATABASES],
      }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar", lang: "en" });
    expect(await screen.findByText("2 classes · 1 reminder")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tomorrow · Wednesday, September 30" }));
    expect(screen.getByText("1 class")).toBeInTheDocument();
  });

  it("labels the week by the picked day, not by the window's first labelled day", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    // The timetable's week changes on Thursday, and Wednesday falls outside every label.
    const labels: Record<string, string | null> = {
      "2026-09-28": "5 неделя", "2026-09-29": "5 неделя", "2026-09-30": null,
      "2026-10-01": "6 неделя", "2026-10-02": "6 неделя", "2026-10-03": "6 неделя", "2026-10-04": "6 неделя",
    };
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": {
        days: weekOf("2026-09-28").map((date) => ({ date, label: labels[date] ?? null, items: [] })),
      },
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByText("5 неделя · 28 сент. – 4 окт.")).toBeInTheDocument(); // Tuesday
    fireEvent.click(screen.getByRole("button", { name: "Послезавтра · четверг, 1 октября" }));
    expect(screen.getByText("6 неделя · 28 сент. – 4 окт.")).toBeInTheDocument();
    // A day without a label of its own falls back to the first label of the window.
    fireEvent.click(screen.getByRole("button", { name: "Завтра · среда, 30 сентября" }));
    expect(screen.getByText("5 неделя · 28 сент. – 4 окт.")).toBeInTheDocument();
  });
});

describe("Calendar dots", () => {
  const PERIODS: [start: string, end: string][] = [
    ["09:00", "10:30"], ["10:40", "12:10"], ["12:40", "14:10"], ["14:20", "15:50"], ["16:00", "17:30"],
  ];
  /** A day's first `count` lessons, one after another. */
  const classes = (count: number) =>
    PERIODS.slice(0, count).map(([start, end], index) => lesson(start, end, `Пара ${index + 1}`));
  /** A day's reminders, in the evening — after the lessons, as in a real timetable day. */
  const reminders = (count: number) =>
    Array.from({ length: count }, (_, index) => item(20 + index, `${18 + index}:00`, `Дело ${index + 1}`));
  /** The dots of a calendar cell, left to right: a lesson's (mint) or a reminder's (amber). */
  const dotKinds = (cell: HTMLElement) =>
    Array.from(cell.querySelectorAll(".cal-dot"), (dot) =>
      dot.classList.contains("cal-dot--lesson") ? "lesson" : "reminder",
    );

  it("leaves a dot for a reminder after at most two lesson dots", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", {
        "2026-09-28": [...classes(3), ...reminders(1)],
        "2026-09-29": [...classes(1), ...reminders(4)],
        "2026-09-30": classes(5),
        "2026-10-01": reminders(4),
      }),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    expect(await screen.findByText("1 пара · 4 напоминания")).toBeInTheDocument();
    const cell = (name: string) => screen.getByRole("button", { name });
    expect(dotKinds(cell("Вчера · понедельник, 28 сентября"))).toEqual(["lesson", "lesson", "reminder"]);
    expect(dotKinds(cell("Сегодня · вторник, 29 сентября"))).toEqual(["lesson", "reminder", "reminder"]);
    // Only one kind: up to three of it, as before.
    expect(dotKinds(cell("Завтра · среда, 30 сентября"))).toEqual(["lesson", "lesson", "lesson"]);
    expect(dotKinds(cell("Послезавтра · четверг, 1 октября"))).toEqual(["reminder", "reminder", "reminder"]);
  });

  it("draws the same dots in the month grid", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    const busy = { "2026-09-29": [...classes(3), ...reminders(1)] };
    mockApi({
      "GET /me": me,
      "GET /agenda?from=2026-09-28&to=2026-10-04": week("2026-09-28", busy),
      "GET /agenda?from=2026-08-31&to=2026-10-04": range("2026-08-31", "2026-10-04", busy),
    });
    renderWithApp(<CalendarScreen />, { path: "/calendar" });
    fireEvent.click(await screen.findByRole("button", { name: "Календарь Показать месяц" }));
    const cell = await screen.findByRole("button", {
      name: "Сегодня · вторник, 29 сентября, 3 пары · 1 напоминание",
    });
    expect(dotKinds(cell)).toEqual(["lesson", "lesson", "reminder"]);
  });
});
