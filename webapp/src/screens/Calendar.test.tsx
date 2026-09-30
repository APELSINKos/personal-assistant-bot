import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgendaItem } from "../api/types";
import { weekOf } from "../lib/format";
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
    fireEvent.click(await screen.findByRole("button", { name: "Показать месяц" }));
    expect(screen.getByText("Сентябрь 2026")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("gridcell", { name: "15" }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Вторник, 15 сентября");
    expect(screen.queryByText("Сентябрь 2026")).not.toBeInTheDocument();
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
