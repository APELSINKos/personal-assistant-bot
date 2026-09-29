import { fireEvent, screen, waitFor } from "@testing-library/react";
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
    expect(container.querySelectorAll(".dot")).toHaveLength(9);
    await waitFor(() => expect(client.getQueryData(["me"])).toBeDefined()); // the city's zone
    fireEvent.click(screen.getByRole("button", { name: /Спорт: без отметки/ }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-29", body: { done: true } }),
    );
  });

  it("deletes a habit after confirming with its name", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "GET /habits": [habit], "DELETE /habits/7": { status: 204 } });
    renderWithApp(<HabitsScreen />);
    fireEvent.click(await screen.findByRole("button", { name: "Удалить привычку «Спорт»" }));
    await waitFor(() => expect(calls).toContainEqual({ method: "DELETE", path: "/habits/7", body: undefined }));
    expect(app.showConfirm).toHaveBeenCalledWith(
      "Удалить привычку «Спорт» вместе со всей статистикой?", expect.any(Function),
    );
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
    expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toEqual([
      { name: "Спорт" }, { name: "Чтение" },
    ]);
  });
});
