import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgendaItem } from "../api/types";
import { addDaysIso, weekOf } from "../lib/format";
import { installTelegram } from "../test/fakeTelegram";
import { me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { CalendarScreen } from "./Calendar";

function item(id: number, time: string, text: string, extra: Partial<AgendaItem> = {}): AgendaItem {
  return { kind: "reminder", id, time, text, repeat: "none", description: null, ...extra };
}

function week(monday: string, items: Record<string, AgendaItem[]> = {}) {
  return { days: weekOf(monday).map((date) => ({ date, items: items[date] ?? [] })) };
}

/** Every day between `fromIso` and `toIso` inclusive — for mocking a month-sized agenda range. */
function range(fromIso: string, toIso: string, items: Record<string, AgendaItem[]> = {}) {
  const days: { date: string; items: AgendaItem[] }[] = [];
  for (let iso = fromIso; iso <= toIso; iso = addDaysIso(iso, 1)) {
    days.push({ date: iso, items: items[iso] ?? [] });
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
