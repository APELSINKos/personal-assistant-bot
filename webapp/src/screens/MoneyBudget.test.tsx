import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { me, moneyCategories } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoneyBudget } from "./MoneyBudget";

describe("Budget", () => {
  it("changes the total, sets one category's budget and takes another's off", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": { ...me, money_budget: 3000000 },
      "GET /money/categories": moneyCategories,
      "PUT /money/budget": { ...me, money_budget: 3500000 },
      "PATCH /money/categories/1": { ...moneyCategories[0], budget: 800000 },
      "PATCH /money/categories/2": { ...moneyCategories[1], budget: null },
    });
    const { history } = renderWithApp(<MoneyBudget />, { path: "/money/budget" });
    expect(await screen.findByLabelText("Общий")).toHaveValue("30000");
    expect(screen.getByLabelText("☕ Кафе")).toHaveValue("5000");
    expect(screen.queryByLabelText("👕 Одежда")).not.toBeInTheDocument(); // hidden, without a budget
    expect(screen.queryByLabelText("🎓 Стипендия")).not.toBeInTheDocument(); // an income
    fireEvent.change(screen.getByLabelText("Общий"), { target: { value: "35 000" } });
    fireEvent.change(screen.getByLabelText("🛒 Продукты"), { target: { value: "8000" } });
    fireEvent.change(screen.getByLabelText("☕ Кафе"), { target: { value: "" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money"));
    expect(calls.filter((call) => call.method !== "GET")).toEqual([
      { method: "PUT", path: "/money/budget", body: { amount: "35000" } },
      { method: "PATCH", path: "/money/categories/1", body: { budget: "8000" } },
      { method: "PATCH", path: "/money/categories/2", body: { budget: null } },
    ]);
  });

  it("will not save a wrong amount", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /money/categories": moneyCategories });
    renderWithApp(<MoneyBudget />, { path: "/money/budget" });
    fireEvent.change(await screen.findByLabelText("Общий"), { target: { value: "много" } });
    expect(screen.getByText("Сумма — число больше нуля, не больше двух знаков после запятой")).toBeInTheDocument();
    expect(vi.mocked(app.MainButton.setParams).mock.calls.at(-1)?.[0].is_active).toBe(false);
  });
});
