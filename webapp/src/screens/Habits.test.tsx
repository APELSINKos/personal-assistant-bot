import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { habit, me } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { HabitForm } from "./HabitForm";
import { HabitsScreen } from "./Habits";

describe("Habits", () => {
  it("shows statistics and marks today in the city's day", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T22:30:00Z")); // 01:30 on the 29th in Moscow
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /habits": [habit],
      "PUT /habits/7/marks/2026-09-29": { ...habit, done_today: true },
    });
    const { container, client } = renderWithApp(<HabitsScreen />);
    expect(await screen.findByText("Спорт")).toBeInTheDocument();
    expect(screen.getByText(/12 из 17 дней/)).toBeInTheDocument();
    expect(screen.getByText(/🔥 5 дней/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Спорт/ })).toHaveAttribute("href", "/habits/7");
    expect(container.querySelectorAll(".dot")).toHaveLength(7); // this week, Monday to Sunday
    await waitFor(() => expect(client.getQueryData(["me"])).toBeDefined()); // the city's zone
    fireEvent.click(screen.getByRole("button", { name: /Спорт: без отметки/ }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-29", body: { done: true } }),
    );
  });

  it("waits for the city's zone before a habit can be marked", async () => {
    installTelegram();
    let answerMe!: (reply: unknown) => void;
    const { calls } = mockApi({
      "GET /me": () => new Promise((resolve) => (answerMe = resolve)),
      "GET /habits": [habit],
    });
    renderWithApp(<HabitsScreen />);
    const toggle = await screen.findByRole("button", { name: /Спорт: без отметки/ });
    expect(toggle).toBeDisabled(); // "today" on the device may be another day than in the city
    fireEvent.click(toggle);
    act(() => answerMe({ body: me }));
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(calls.filter((call) => call.method === "PUT")).toEqual([]);
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

  it("says the habit is gone when it was deleted elsewhere", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /habits/7": { status: 404, body: { status: 404, code: "not_found" } } });
    renderWithApp(<HabitForm />, { path: "/habits/7/edit" });
    expect(await screen.findByText("Этой привычки уже нет.")).toBeInTheDocument();
  });
});
