import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import type { TgWebApp } from "../telegram";
import { installTelegram } from "../test/fakeTelegram";
import { habit, me } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { HabitForm } from "./HabitForm";
import { HabitsScreen } from "./Habits";

const RATE_LIMITED = { status: 429, body: { status: 429, code: "rate_limited", title: "Too many requests" } };

/** Whether Telegram's main button («Сохранить») can be pressed now. */
function canSave(app: TgWebApp): boolean | undefined {
  return vi.mocked(app.MainButton.setParams).mock.calls.at(-1)?.[0].is_active;
}

describe("Habits", () => {
  it("shows statistics and marks the day the list is for, even when the tap comes after midnight", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T20:59:30Z")); // 23:59:30 on the 28th in Moscow
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /habits": [habit], // counted for the 28th
      "PUT /habits/7/marks/2026-09-28": { ...habit, done_today: true },
    });
    const { container } = renderWithApp(<HabitsScreen />);
    expect(await screen.findByText("Спорт")).toBeInTheDocument();
    expect(screen.getByText(/12 из 17 дней/)).toBeInTheDocument();
    expect(screen.getByText(/🔥 5 дней/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Спорт/ })).toHaveAttribute("href", "/habits/7");
    expect(container.querySelectorAll(".dot")).toHaveLength(7); // this week, Monday to Sunday
    vi.setSystemTime(new Date("2026-09-28T21:00:30Z")); // 00:00:30 on the 29th
    fireEvent.click(screen.getByRole("button", { name: /Спорт: без отметки/ }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-28", body: { done: true } }),
    );
  });

  it("marks without waiting for the user's city: the day comes with the list", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": () => new Promise(() => undefined), // never answers
      "GET /habits": [habit],
      "PUT /habits/7/marks/2026-09-28": { ...habit, done_today: true },
    });
    renderWithApp(<HabitsScreen />);
    fireEvent.click(await screen.findByRole("button", { name: /Спорт: без отметки/ }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-28", body: { done: true } }),
    );
  });

  it("keeps the list and its toggles when only a refresh fails", async () => {
    installTelegram();
    mockApi({ "GET /habits": [habit] });
    const { client } = renderWithApp(<HabitsScreen />);
    await screen.findByRole("button", { name: /Спорт: без отметки/ });
    mockApi({ "GET /habits": RATE_LIMITED });
    await act(async () => {
      await client.refetchQueries({ queryKey: ["habits"] });
      await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
    });
    expect(screen.getByRole("button", { name: /Спорт: без отметки/ })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
  });

  it("shows a weekly habit's week and a streak of weeks", async () => {
    installTelegram();
    const weekly = {
      ...habit, emoji: "🏃", color: "sky" as const, weekly_goal: 3, streak: 2, streak_unit: "weeks" as const,
      week_done: 2, week_goal: 3, week: "10-1...",
    };
    mockApi({ "GET /me": me, "GET /habits": [weekly] });
    const { container } = renderWithApp(<HabitsScreen />);
    expect(await screen.findByText("🔥 2 недели · 2 из 3 на этой неделе")).toBeInTheDocument();
    expect(screen.getByText("🏃")).toBeInTheDocument();
    const dots = Array.from(container.querySelectorAll(".dot"), (dot) => dot.className);
    expect(dots).toEqual([
      "dot dot--done", "dot dot--skipped", "dot", "dot dot--done", "dot dot--ahead", "dot dot--ahead", "dot dot--ahead",
    ]);
    expect(screen.queryByRole("button", { name: /^Удалить/ })).not.toBeInTheDocument(); // on the habit's screen now
  });

  it("adds a habit and reports a duplicate", async () => {
    const app = installTelegram();
    let first = true;
    const { calls } = mockApi({
      "GET /me": me,
      "POST /habits": () => {
        if (first) {
          first = false;
          return {
            status: 422,
            body: { status: 422, code: "validation_error", title: "x", field: "name", reason: "duplicate" },
          };
        }
        return { status: 201, body: { ...habit, id: 8, name: "Чтение" } };
      },
    });
    const { history } = renderWithApp(<><HabitForm /><Toasts /></>, { path: "/habits/new" });
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Спорт" } });
    pressMainButton(app);
    expect(await screen.findByText("Такая уже есть")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Чтение" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/habits"));
    const look = { emoji: "🎯", color: "mint", weekly_goal: 7 };
    expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toEqual([
      { name: "Спорт", ...look }, { name: "Чтение", ...look },
    ]);
  });

  it("asks before leaving a name unsaved, but not an empty one", async () => {
    const app = installTelegram({ showConfirm: vi.fn((_m: string, callback: (ok: boolean) => void) => callback(false)) });
    mockApi({ "GET /me": me });
    const { history } = renderWithApp(<HabitForm />, { path: "/habits/new" });
    const back = () => vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Плавание" } });
    await act(async () => back()?.());
    expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function));
    expect(history.at(-1)).toBe("/habits/new");
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "" } });
    await act(async () => back()?.());
    expect(history.at(-1)).toBe("/habits");
  });
});

describe("Habit form", () => {
  it("creates a habit with a picked emoji, colour and goal", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "POST /habits": { status: 201, body: habit } });
    const { history } = renderWithApp(<HabitForm />, { path: "/habits/new" });
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Бег" } });
    fireEvent.click(screen.getByRole("button", { name: "🏃" }));
    fireEvent.click(screen.getByRole("button", { name: "голубой" }));
    fireEvent.click(screen.getByRole("button", { name: "3 раза в неделю" }));
    expect(screen.getByRole("button", { name: "🏃" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "🎯" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText(/пересчитаются/)).not.toBeInTheDocument(); // a new habit has no history
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/habits"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Бег", emoji: "🏃", color: "sky", weekly_goal: 3,
    });
  });

  it("edits a habit: shows what it has, warns about a new goal, goes back to the habit", async () => {
    const app = installTelegram();
    const detail = { ...habit, year_from: "2025-09-29", year: ".".repeat(371) };
    const { calls } = mockApi({ "GET /me": me, "GET /habits/7": detail, "PATCH /habits/7": habit });
    const { history } = renderWithApp(<HabitForm />, { path: "/habits/7/edit" });
    expect(await screen.findByRole("heading", { name: "Привычка" })).toBeInTheDocument();
    expect(screen.getByLabelText("Название")).toHaveValue("Спорт");
    expect(screen.getByRole("button", { name: "💪" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "мятный" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Каждый день" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "1 раз в неделю" }));
    expect(screen.getByText("Серия и проценты пересчитаются по новой цели.").closest("[aria-live='polite']"))
      .not.toBeNull();
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/habits/7"));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      name: "Спорт", emoji: "💪", color: "mint", weekly_goal: 1,
    });
  });

  it("counts the name in characters as the server does: a name of 30 emoji from the bot is saved", async () => {
    const app = installTelegram();
    const detail = { ...habit, name: "🏃".repeat(30), year_from: "2025-09-29", year: ".".repeat(371) };
    const { calls } = mockApi({ "GET /me": me, "GET /habits/7": detail, "PATCH /habits/7": habit });
    renderWithApp(<HabitForm />, { path: "/habits/7/edit" });
    const field = await screen.findByLabelText("Название");
    expect(field).toHaveValue("🏃".repeat(30)); // 60 UTF-16 units

    fireEvent.change(field, { target: { value: "🏃".repeat(51) } });
    expect(screen.getByText("51/50")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("51/50");
    expect(canSave(app)).toBe(false);

    fireEvent.change(field, { target: { value: "🏃".repeat(50) } });
    expect(screen.queryByText("51/50")).not.toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "false");
    expect(canSave(app)).toBe(true);
    pressMainButton(app);
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ name: "🏃".repeat(50) }));
  });

  it("says the habit is gone when it was deleted elsewhere", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /habits/7": { status: 404, body: { status: 404, code: "not_found" } } });
    renderWithApp(<HabitForm />, { path: "/habits/7/edit" });
    expect(await screen.findByText("Этой привычки уже нет.")).toBeInTheDocument();
  });
});
