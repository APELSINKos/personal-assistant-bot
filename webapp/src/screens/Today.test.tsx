import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
