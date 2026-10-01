import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TodayLesson } from "../api/types";
import { installTelegram } from "../test/fakeTelegram";
import { habit, today } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { TodayScreen } from "./Today";

describe("Today", () => {
  it("shows the whole day", async () => {
    installTelegram();
    mockApi({ "GET /today": today });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("28")).toBeInTheDocument();
    expect(screen.getByText(/понедельник/)).toBeInTheDocument();
    expect(screen.getByText(/сентябрь 2026/)).toBeInTheDocument();
    expect(screen.getByText("+10°")).toBeInTheDocument();
    expect(screen.getByText(/Дождь ожидается после 18:00/)).toBeInTheDocument();
    expect(screen.queryByText(/Утром холодно/)).not.toBeInTheDocument();
    expect(screen.getByText("19:30")).toBeInTheDocument();
    expect(screen.getByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.getByText(/🔥 5 дней/)).toBeInTheDocument();
    expect(screen.getByText(/USD 84,20 ₽/)).toBeInTheDocument();
    expect(screen.getByText("📝 4 заметки")).toBeInTheDocument();
    expect(screen.getByText("🔥 Лучшая серия: «Спорт» — 5 дней")).toBeInTheDocument();
  });

  it("names the best streak in English, and only when there is one", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, best_streak: { name: "Sport", days: 1 } } });
    const { unmount } = renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("🔥 Best streak: “Sport” — 1 day")).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...today, best_streak: null } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.queryByText(/Лучшая серия/)).not.toBeInTheDocument();
  });

  it("marks a habit with one tap", async () => {
    const app = installTelegram();
    let done: boolean | null = null;
    const { calls } = mockApi({
      "GET /today": () => ({
        body: { ...today, habits: { ...today.habits, items: [{ ...habit, done_today: done }] } },
      }),
      "PUT /habits/7/marks/2026-09-28": ({ body }: { body: unknown }) => {
        done = (body as { done: boolean | null }).done;
        return { body: { ...habit, done_today: done } };
      },
    });
    renderWithApp(<TodayScreen />);
    fireEvent.click(await screen.findByRole("button", { name: /Спорт: без отметки/ }));
    expect(await screen.findByRole("button", { name: /Спорт: выполнено/ })).toBeInTheDocument();
    expect(screen.getByText("Привычки · 1 из 1")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-28", body: { done: true } }),
    );
    expect(app.HapticFeedback?.impactOccurred).toHaveBeenCalledWith("light");
  });

  it("test_today_without_weather_and_rates", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, weather: null, rates: null, reminders_today: [] } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Погода временно недоступна")).toBeInTheDocument();
    expect(screen.getByText("Свободный день")).toBeInTheDocument();
    expect(screen.queryByText(/USD/)).not.toBeInTheDocument();
    expect(screen.getByText("Привычки · 0 из 1")).toBeInTheDocument();
  });

  it("offers a retry when the day cannot be loaded", async () => {
    installTelegram();
    mockApi({ "GET /today": { status: 400, body: { status: 400, code: "http_error", title: "Bad" } } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});

describe("Today lessons", () => {
  const lessons: TodayLesson[] = [
    {
      time: "10:40", end: "12:10", title: "Математический анализ", kind: "ЛК", room: "А-16",
      starts_at: "2026-09-28T07:40:00Z", ends_at: "2026-09-28T09:10:00Z",
    },
    {
      time: "12:40", end: "14:10", title: "Разработка баз данных", kind: "ПР", room: null,
      starts_at: "2026-09-28T09:40:00Z", ends_at: "2026-09-28T11:10:00Z",
    },
  ];

  afterEach(() => vi.useRealTimers());

  it("lists the day's lessons, then says they are over", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T08:00:00Z")); // 11:00 in Moscow, during the first one
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: "5 неделя" } });
    const { unmount } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Пары · 5 неделя")).toBeInTheDocument();
    expect(screen.getByText("Математический анализ")).toBeInTheDocument();
    expect(screen.getByText("ЛК · 10:40–12:10 · А-16")).toBeInTheDocument();
    expect(screen.getByText("ПР · 12:40–14:10")).toBeInTheDocument();
    unmount();
    vi.setSystemTime(new Date("2026-09-28T11:10:00Z")); // the last one has just ended
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Пары закончились")).toBeInTheDocument();
    expect(screen.queryByText("Математический анализ")).not.toBeInTheDocument();
  });

  it("has no lessons card without lessons today", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, week_label: "5 неделя" } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.queryByText(/^Пары/)).not.toBeInTheDocument();
  });

  it("names the lessons in English", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T08:00:00Z"));
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("Classes")).toBeInTheDocument();
  });
});
