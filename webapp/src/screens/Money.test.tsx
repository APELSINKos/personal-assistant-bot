import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MoneyMonth } from "../api/types";
import { installTelegram } from "../test/fakeTelegram";
import { me, moneyMonth } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoneyScreen } from "./Money";

// Text queries see a no-break space as a plain one (lib/money.test.ts checks them).
const rub = (amount: string) => `${amount} ₽`;

const AUGUST: MoneyMonth = {
  ...moneyMonth,
  month: "2026-08",
  spent: 0,
  income: 0,
  balance: 0,
  left: 3000000,
  per_day: null,
  expenses: [],
  incomes: [],
  days: Array<number>(31).fill(0),
  entries: [],
};
const NOT_FOUND = { status: 404, body: { status: 404, code: "not_found" } };

function show(routes: Record<string, unknown> = {}, lang: "ru" | "en" = "ru") {
  const api = mockApi({ "GET /me": me, "GET /money?month=2026-09": moneyMonth, ...routes });
  return { ...api, ...renderWithApp(<MoneyScreen />, { path: "/money", lang }) };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-28T09:00:00Z")); // noon in Moscow, Monday
  installTelegram();
});

describe("Money", () => {
  it("shows the month: spent of the budget, the income, the ring, the days and the entries", async () => {
    show();
    expect(await screen.findByText(rub("16 980,50"))).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Сентябрь 2026" })).toBeInTheDocument();
    expect(
      screen.getByText(`из ${rub("30 000")} · осталось ${rub("13 019,50")}, по ${rub("4 339,83")} в день`),
    ).toBeInTheDocument();
    expect(screen.getByText(`Доходы ${rub("3 000")} · баланс −${rub("13 980,50")}`)).toBeInTheDocument();
    const ring = screen.getByRole("img", { name: "Траты по категориям: Дом 88%, Продукты 7%, Кафе 3%, Транспорт 2%" });
    expect(within(ring).getByText("5")).toBeInTheDocument();
    expect(within(ring).getByText("записей")).toBeInTheDocument();
    const cafe = screen.getByRole("button", { name: /☕ Кафе/ });
    expect(within(cafe).getByText(rub("430,50"))).toBeInTheDocument();
    expect(within(cafe).getByText("3%")).toBeInTheDocument();
    expect(screen.getByText(`из ${rub("5 000")} · осталось ${rub("4 569,50")}`)).toBeInTheDocument();
    // A role's name keeps its no-break spaces, which \s matches.
    expect(screen.getByRole("img", { name: /^Траты по дням; больше всего — 1 сентября: 15\s000\s₽$/ })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual([
      "Сегодня", "Вчера", "пт, 25 сент.", "вт, 1 сент.",
    ]);
    expect(screen.getByText("кофе")).toBeInTheDocument();
    expect(screen.getByText(`+${rub("3 000")}`)).toBeInTheDocument();
  });

  it("shows only a category's entries after a tap on it in the legend", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: /☕ Кафе/ }));
    expect(screen.getByRole("button", { name: /☕ Кафе/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("кофе")).toBeInTheDocument();
    expect(screen.queryByText("такси")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать все записи, не только «Кафе»" }));
    expect(screen.getByText("такси")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /☕ Кафе/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("goes back month by month to the first entry's, and not past this one", async () => {
    const { calls } = show({ "GET /money?month=2026-08": AUGUST });
    await screen.findByText("кофе");
    expect(screen.getByRole("button", { name: "Следующий месяц" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Предыдущий месяц" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Август 2026" })).toBeInTheDocument();
    expect(await screen.findByText("В этом месяце записей нет.")).toBeInTheDocument();
    expect(screen.getByText(`из ${rub("30 000")} · осталось ${rub("30 000")}`)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument(); // nothing spent: no charts
    expect(screen.getByRole("button", { name: "Предыдущий месяц" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Следующий месяц" }));
    expect(await screen.findByText("кофе")).toBeInTheDocument();
    expect(calls.map((call) => call.path)).toContain("/money?month=2026-08");
  });

  it("deletes an entry swiped away", async () => {
    let month = moneyMonth;
    const { calls } = show({
      "GET /money?month=2026-09": () => ({ body: month }),
      "DELETE /money/entries/24": () => {
        month = { ...moneyMonth, entries: moneyMonth.entries.slice(1) };
        return { status: 204 };
      },
    });
    const row = (await screen.findByText("кофе")).closest(".swipe") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Удалить запись" }));
    await waitFor(() => expect(screen.queryByText("кофе")).not.toBeInTheDocument());
    expect(calls).toContainEqual({ method: "DELETE", path: "/money/entries/24", body: undefined });
  });

  it("offers a retry when the user or the month cannot be read", async () => {
    const first = show({ "GET /me": NOT_FOUND });
    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
    first.unmount();
    show({ "GET /money?month=2026-09": NOT_FOUND });
    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Сентябрь 2026" })).toBeInTheDocument();
  });

  it("speaks English in the user's currency, without a budget", async () => {
    show({ "GET /money?month=2026-09": { ...moneyMonth, currency: "USD", budget: null, left: null, per_day: null } }, "en");
    expect(await screen.findByText("$16,980.50")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "September 2026" })).toBeInTheDocument();
    expect(screen.getByText("Income $3,000 · balance −$13,980.50")).toBeInTheDocument();
    expect(screen.queryByText(/^of \$30,000/)).not.toBeInTheDocument();
    expect(screen.getByText("of $5,000 · $4,569.50 left")).toBeInTheDocument(); // the category's own
    expect(screen.getByRole("heading", { level: 3, name: "Fri, Sep 25" })).toBeInTheDocument();
  });
});

describe("Money's ways on", () => {
  it("lead to a new entry, an entry's form, the budget and the categories", async () => {
    show({ "GET /money?month=2026-09": { ...moneyMonth, budget: null, left: null, per_day: null } });
    expect(await screen.findByRole("link", { name: "Задать бюджет" })).toHaveAttribute("href", "/money/budget");
    expect(screen.getByRole("link", { name: "Добавить запись" })).toHaveAttribute("href", "/money/new");
    expect(screen.getByRole("link", { name: "🎯 Бюджет" })).toHaveAttribute("href", "/money/budget");
    expect(screen.getByRole("link", { name: "🗂 Категории" })).toHaveAttribute("href", "/money/categories");
    expect(screen.getByText("кофе").closest("a")).toHaveAttribute("href", "/money/24/edit");
  });
});

describe("Money's rates", () => {
  const rates = {
    date: "2026-09-28",
    currencies: [
      { code: "USD", name: "Доллар США", value: 82.6417, change: -0.45 },
      { code: "EUR", name: "Евро", value: 96.1234, change: 0.31 },
      { code: "AMD", name: "Армянский драм", value: 0.2149, change: 0 },
    ],
  };
  const days = { code: "USD", points: [{ day: "2026-09-26", value: 84 }, { day: "2026-09-27", value: 82.64 }] };

  it("show the dollar and the euro of the day and lead to the rates", async () => {
    show({ "GET /rates/all": rates, "GET /rates/history?code=USD": days, "GET /rates/history?code=EUR": days });
    const card = await screen.findByRole("link", { name: /Курсы ЦБ/ });
    expect(card).toHaveAttribute("href", "/money/rates");
    expect(await within(card).findByText("82,64 ₽")).toBeInTheDocument();
    expect(within(card).getByText("96,12 ₽")).toBeInTheDocument();
    expect(within(card).getByText("▲ 0,31")).toBeInTheDocument();
    expect(within(card).queryByText("AMD")).not.toBeInTheDocument(); // not the user's currency
  });

  it("say when the bank's rates cannot be had", async () => {
    show({ "GET /rates/all": NOT_FOUND });
    const card = await screen.findByRole("link", { name: /Курсы ЦБ/ });
    expect(await within(card).findByText("Курсы ЦБ сейчас недоступны")).toBeInTheDocument();
  });
});
