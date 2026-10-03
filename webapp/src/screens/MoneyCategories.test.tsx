import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { moneyCategories } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoneyCategories, MoneyCategoryForm } from "./MoneyCategories";

describe("Categories", () => {
  it("lists the expenses and the incomes, the hidden ones marked", async () => {
    installTelegram();
    mockApi({ "GET /money/categories": moneyCategories });
    renderWithApp(<MoneyCategories />, { path: "/money/categories" });
    expect(await screen.findByRole("link", { name: /Продукты/ })).toHaveAttribute("href", "/money/categories/1");
    expect(screen.getByRole("link", { name: /Одежда/ })).toHaveTextContent("скрыта");
    expect(screen.getByRole("heading", { name: "Доходы" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Новая категория" })).toHaveAttribute("href", "/money/categories/new");
  });

  it("says when there is no room for one more category", async () => {
    installTelegram();
    const many = Array.from({ length: 40 }, (_, index) => ({
      ...moneyCategories[index % moneyCategories.length], id: 100 + index, name: `Своя ${index}`,
    }));
    mockApi({ "GET /money/categories": many });
    renderWithApp(<MoneyCategories />, { path: "/money/categories" });
    expect(
      await screen.findByText("Категорий уже 40 — новую не добавить. Ненужную можно переименовать."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Новая категория" })).not.toBeInTheDocument();
  });

  it("makes a new income category with its emoji", async () => {
    const app = installTelegram();
    const made = { id: 9, kind: "income", name: "Подработка", emoji: "💼", hidden: false, can_hide: true, budget: null };
    const { calls } = mockApi({
      "GET /money/categories": moneyCategories, "POST /money/categories": { status: 201, body: made },
    });
    const { history } = renderWithApp(<MoneyCategoryForm />, { path: "/money/categories/new" });
    fireEvent.click(await screen.findByRole("button", { name: "Доход" }));
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: " Подработка " } });
    fireEvent.click(screen.getByRole("button", { name: "💼" }));
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money/categories"));
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({ kind: "income", name: "Подработка", emoji: "💼" });
  });

  it("renames and hides a category, sending only what changed", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /money/categories": moneyCategories,
      "PATCH /money/categories/2": { ...moneyCategories[1], name: "Кофейни", hidden: true },
    });
    const { history } = renderWithApp(<MoneyCategoryForm />, { path: "/money/categories/2" });
    expect(await screen.findByLabelText("Название")).toHaveValue("Кафе");
    expect(screen.getByRole("button", { name: "☕" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Кофейни" } });
    fireEvent.click(screen.getByRole("switch", { name: "Скрыть категорию" }));
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money/categories"));
    expect(calls.find((call) => call.method === "PATCH")).toMatchObject({
      path: "/money/categories/2", body: { name: "Кофейни", hidden: true },
    });
  });

  it("keeps «Другое» visible, and says when a category does not exist", async () => {
    installTelegram();
    mockApi({ "GET /money/categories": moneyCategories });
    const { unmount } = renderWithApp(<MoneyCategoryForm />, { path: "/money/categories/6" });
    expect(await screen.findByText(/«Другое» скрыть нельзя/)).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    unmount();
    renderWithApp(<MoneyCategoryForm />, { path: "/money/categories/99" });
    expect(await screen.findByText("Этой категории нет.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "К категориям" })).toHaveAttribute("href", "/money/categories");
  });
});
