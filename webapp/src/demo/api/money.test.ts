import { describe, expect, it } from "vitest";
import type {
  Me, MoneyCategory, MoneyEntry, MoneyEntrySaved, MoneyMonth, RateHistory, RatesAll,
} from "../../api/types";
import { CURRENCY_CODES } from "../../lib/money";
import { demoApi, problem } from "./testApi";

const NO_CONTENT = { status: 204, body: null, headers: {} };

/** The demo with no money noted yet: the categories and the budgets only. */
function emptyMoney(language: "ru" | "en" = "ru") {
  const demo = demoApi(language);
  demo.visit.data.entries = [];
  demo.visit.data.alerts.clear();
  return demo;
}

/** An entry as the form sends it: in the user's currency, a decimal with a point. */
const entry = (amount: string, category_id: number, day = "2026-10-07", note = "") => ({ amount, category_id, note, day });

describe("a month of money (routers/money.py, services/money_month.py)", () => {
  it("GET /money: the month's totals, by category and by day, and the budget's rest", () => {
    const { read } = emptyMoney();
    read("POST /money/entries", entry("250", 2, "2026-10-01", "кофе"));
    read("POST /money/entries", entry("1200.50", 1, "2026-10-03", "продукты"));
    read("POST /money/entries", entry("750", 2, "2026-10-07", "обед"));
    read("POST /money/entries", entry("20000", 13, "2026-10-05", "подработка"));
    read("POST /money/entries", entry("500", 1, "2026-09-30"));
    const month = read<MoneyMonth>("GET /money");
    expect(month).toMatchObject({
      month: "2026-10", first_month: "2026-09", currency: "RUB", spent: 220_050, income: 2_000_000, balance: 1_779_950,
      budget: 3_000_000, left: 2_779_950, per_day: Math.floor(2_779_950 / 25),
      expenses: [
        { category_id: 1, amount: 120_050, share: 55, left: null },
        { category_id: 2, amount: 100_000, share: 45, left: 300_000 },
      ],
      incomes: [{ category_id: 13, amount: 2_000_000, share: 0, left: null }],
    });
    expect(month.days).toEqual([25_000, 0, 120_050, 0, 0, 0, 75_000, ...Array.from({ length: 24 }, () => null)]);
    expect(month.categories).toHaveLength(16);
    expect(month.categories[1]).toEqual({ id: 2, kind: "expense", name: "Кафе", emoji: "☕", hidden: false, can_hide: true, budget: 400_000 });
    expect(month.categories[11]).toMatchObject({ name: "Другое", can_hide: false });
    expect(month.entries.map((item) => item.day)).toEqual(["2026-10-07", "2026-10-05", "2026-10-03", "2026-10-01"]);
  });

  it("GET /money?month=: a past month whole, and the month as the server checks it", () => {
    const { read, call } = demoApi();
    const august = read<MoneyMonth>("GET /money?month=2026-08");
    expect(august.month).toBe("2026-08");
    expect(august.days).toHaveLength(31);
    expect(august.days.every((day) => day !== null)).toBe(true);
    expect(august.per_day).toBeNull();
    expect(august.spent).toBeGreaterThan(0);
    expect(call("GET /money?month=2026-13")).toEqual(problem(422, "validation_error", { field: "month", reason: "format" }));
    expect(call("GET /money?month=1999-01")).toEqual(problem(422, "validation_error", { field: "month", reason: "range" }));
    expect(call("GET /money?month=2026-1")).toEqual(problem(422, "validation_error", { field: "month" }));
  });

  it("names the categories in the user's language", () => {
    const { read } = demoApi("en");
    expect(read<MoneyCategory[]>("GET /money/categories").map((category) => category.name).slice(0, 3)).toEqual([
      "Groceries", "Eating out", "Transport",
    ]);
  });
});

describe("the entries (routers/money.py, services/money.py)", () => {
  it("POST /money/entries: an amount above zero up to a billion, a known category, a day of the last year", () => {
    const { call } = emptyMoney();
    expect(call("POST /money/entries", { amount: "430.5", category_id: 1, note: " хлеб\tи молоко " })).toEqual({
      status: 201,
      body: { entry: { id: expect.any(Number), amount: 43_050, category_id: 1, note: "хлеб и молоко", day: "2026-10-07" }, alerts: [] },
      headers: { "Content-Type": "application/json" },
    });
    expect(call("POST /money/entries", entry("0", 1))).toEqual(problem(422, "validation_error", { field: "amount", reason: "out_of_range" }));
    expect(call("POST /money/entries", entry("1000000000.01", 1))).toEqual(
      problem(422, "validation_error", { field: "amount", reason: "out_of_range" }),
    );
    expect(call("POST /money/entries", entry("1000000000", 1)).status).toBe(201);
    expect(call("POST /money/entries", entry("12.345", 1))).toEqual(problem(422, "validation_error", { field: "amount" }));
    expect(call("POST /money/entries", entry("10", 99))).toEqual(problem(404, "not_found", { entity: "category" }));
    expect(call("POST /money/entries", entry("10", 1, "2026-10-07", "я".repeat(101)))).toEqual(
      problem(422, "validation_error", { field: "note", reason: "length", limit: 100 }),
    );
    expect(call("POST /money/entries", entry("10", 1, "2025-10-05"))).toEqual(
      problem(422, "validation_error", { field: "day", reason: "out_of_range" }),
    );
    expect(call("POST /money/entries", entry("10", 1, "2025-10-06")).status).toBe(201);
    expect(call("POST /money/entries", entry("10", 1, "2026-10-08"))).toEqual(
      problem(422, "validation_error", { field: "day", reason: "out_of_range" }),
    );
  });

  it("GET /money/entries/{entry_id}: one entry for its form", () => {
    const { read, call } = demoApi();
    const [first] = read<MoneyMonth>("GET /money").entries;
    expect(read<MoneyEntry>(`GET /money/entries/${first?.id}`)).toEqual(first);
    expect(call("GET /money/entries/999999")).toEqual(problem(404, "not_found", { entity: "entry" }));
  });

  it("PATCH /money/entries/{entry_id}: any field, an expense may become an income", () => {
    const { read, call } = emptyMoney();
    const { entry: saved } = read<MoneyEntrySaved>("POST /money/entries", entry("100", 1, "2026-10-02", "сдача"));
    expect(read<MoneyEntrySaved>(`PATCH /money/entries/${saved.id}`, { amount: "150", category_id: 16, day: "2026-10-03" })).toEqual({
      entry: { id: saved.id, amount: 15_000, category_id: 16, note: "сдача", day: "2026-10-03" }, alerts: [],
    });
    expect(read<MoneyMonth>("GET /money")).toMatchObject({ spent: 0, income: 15_000 });
    expect(call(`PATCH /money/entries/${saved.id}`, { category_id: 99 })).toEqual(problem(404, "not_found", { entity: "category" }));
    expect(call(`PATCH /money/entries/${saved.id}`, { day: "2026-10-08" })).toEqual(
      problem(422, "validation_error", { field: "day", reason: "out_of_range" }),
    );
    expect(call(`PATCH /money/entries/${saved.id}`, { amount: "-5" })).toEqual(problem(422, "validation_error", { field: "amount" }));
    expect(call("PATCH /money/entries/999999", { amount: "5" })).toEqual(problem(404, "not_found", { entity: "entry" }));
  });

  it("DELETE /money/entries/{entry_id}: gone, then 404", () => {
    const { read, call } = emptyMoney();
    const { entry: saved } = read<MoneyEntrySaved>("POST /money/entries", entry("100", 1));
    expect(call(`DELETE /money/entries/${saved.id}`)).toEqual(NO_CONTENT);
    expect(read<MoneyMonth>("GET /money").entries).toEqual([]);
    expect(call(`DELETE /money/entries/${saved.id}`)).toEqual(problem(404, "not_found", { entity: "entry" }));
  });
});

describe("the budget warnings (money_month.alerts_after)", () => {
  it("warn at 80 % and at 100 %, once a month per budget and threshold", () => {
    const { read } = emptyMoney();
    const alerts = (amount: string, category: number) =>
      read<MoneyEntrySaved>("POST /money/entries", entry(amount, category)).alerts;
    expect(alerts("23999", 1)).toEqual([]);
    expect(alerts("1", 1)).toEqual([{ category_id: null, emoji: null, name: null, threshold: 80, spent: 2_400_000, budget: 3_000_000 }]);
    expect(alerts("100", 1)).toEqual([]);
    expect(alerts("5900", 1)).toEqual([{ category_id: null, emoji: null, name: null, threshold: 100, spent: 3_000_000, budget: 3_000_000 }]);
    expect(alerts("3200", 2)).toEqual([
      { category_id: 2, emoji: "☕", name: "Кафе", threshold: 80, spent: 320_000, budget: 400_000 },
    ]);
  });

  it("show the higher of two thresholds reached at once, and none for an income or another month", () => {
    const { read } = emptyMoney();
    expect(read<MoneyEntrySaved>("POST /money/entries", entry("3500", 8)).alerts).toEqual([
      { category_id: 8, emoji: "🎮", name: "Развлечения", threshold: 100, spent: 350_000, budget: 300_000 },
    ]);
    expect(read<MoneyEntrySaved>("POST /money/entries", entry("50000", 14)).alerts).toEqual([]);
    expect(read<MoneyEntrySaved>("POST /money/entries", entry("50000", 1, "2026-09-20")).alerts).toEqual([]);
  });

  it("warn again once an entry undone took the spending back under the threshold, or the budget changed", () => {
    const { read, call } = emptyMoney();
    const big = read<MoneyEntrySaved>("POST /money/entries", entry("24000", 1));
    expect(big.alerts.map((alert) => alert.threshold)).toEqual([80]);
    call(`DELETE /money/entries/${big.entry.id}`);
    expect(read<MoneyEntrySaved>("POST /money/entries", entry("24000", 1)).alerts.map((alert) => alert.threshold)).toEqual([80]);
    read("PUT /money/budget", { amount: "25000" });
    expect(read<MoneyEntrySaved>("POST /money/entries", entry("1", 1)).alerts).toEqual([
      { category_id: null, emoji: null, name: null, threshold: 80, spent: 2_400_100, budget: 2_500_000 },
    ]);
    const moved = read<MoneyEntrySaved>("POST /money/entries", entry("3200", 2));
    expect(moved.alerts.map((alert) => [alert.category_id, alert.threshold])).toEqual([[2, 80], [null, 100]]);
  });
});

describe("the categories (routers/money.py, services/money.py)", () => {
  it("GET /money/categories: the twelve and four presets in the user's language", () => {
    const categories = demoApi().read<MoneyCategory[]>("GET /money/categories");
    expect(categories.map((category) => [category.kind, category.name, category.emoji])).toEqual([
      ["expense", "Продукты", "🛒"], ["expense", "Кафе", "☕"], ["expense", "Транспорт", "🚌"], ["expense", "Дом", "🏠"],
      ["expense", "Связь", "📱"], ["expense", "Здоровье", "💊"], ["expense", "Одежда", "👕"], ["expense", "Развлечения", "🎮"],
      ["expense", "Учёба", "📚"], ["expense", "Подарки", "🎁"], ["expense", "Подписки", "📺"], ["expense", "Другое", "📦"],
      ["income", "Зарплата", "💼"], ["income", "Стипендия", "🎓"], ["income", "Подарили", "🎀"], ["income", "Другое", "💰"],
    ]);
  });

  it("POST /money/categories: a name of its own, an emoji of the set, up to forty in all", () => {
    const { call } = demoApi();
    expect(call("POST /money/categories", { kind: "expense", name: " Кофейни ", emoji: "☕" })).toEqual({
      status: 201,
      body: { id: 17, kind: "expense", name: "Кофейни", emoji: "☕", hidden: false, can_hide: true, budget: null },
      headers: { "Content-Type": "application/json" },
    });
    expect(call("POST /money/categories", { kind: "expense", name: "groceries", emoji: "🛒" })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "duplicate" }),
    );
    expect(call("POST /money/categories", { kind: "income", name: "Продукты", emoji: "💰" }).status).toBe(201);
    expect(call("POST /money/categories", { kind: "expense", name: "КОФЕЙНИ", emoji: "☕" })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "duplicate" }),
    );
    expect(call("POST /money/categories", { kind: "expense", name: " ", emoji: "☕" })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "empty" }),
    );
    expect(call("POST /money/categories", { kind: "expense", name: "я".repeat(31), emoji: "☕" })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "length", limit: 30 }),
    );
    expect(call("POST /money/categories", { kind: "expense", name: "Единороги", emoji: "🦄" })).toEqual(
      problem(422, "validation_error", { field: "emoji", reason: "not_in_set" }),
    );
    expect(call("POST /money/categories", { kind: "debt", name: "Долги", emoji: "💳" })).toEqual(
      problem(422, "validation_error", { field: "kind" }),
    );
    for (let count = 19; count <= 40; count += 1) {
      expect(call("POST /money/categories", { kind: "expense", name: `Траты ${count}`, emoji: "💳" }).status).toBe(201);
    }
    expect(call("POST /money/categories", { kind: "expense", name: "Ещё", emoji: "💳" })).toEqual(
      problem(409, "limit_reached", { entity: "category", limit: 40 }),
    );
  });

  it("PATCH /money/categories/{category_id}: renamed, another emoji, hidden, with a budget or without", () => {
    const { read, call } = demoApi();
    expect(read<MoneyCategory>("PATCH /money/categories/1", { name: "Еда", emoji: "🍕", budget: "12000" })).toEqual({
      id: 1, kind: "expense", name: "Еда", emoji: "🍕", hidden: false, can_hide: true, budget: 1_200_000,
    });
    expect(read<MoneyCategory>("PATCH /money/categories/1", { hidden: true, budget: null })).toMatchObject({ hidden: true, budget: null });
    expect(call("PATCH /money/categories/12", { hidden: true })).toEqual(
      problem(422, "validation_error", { field: "hidden", reason: "fallback" }),
    );
    expect(call("PATCH /money/categories/14", { budget: "100" })).toEqual(
      problem(422, "validation_error", { field: "budget", reason: "income" }),
    );
    expect(call("PATCH /money/categories/2", { budget: "0" })).toEqual(
      problem(422, "validation_error", { field: "budget", reason: "out_of_range" }),
    );
    expect(call("PATCH /money/categories/2", { name: "Транспорт" })).toEqual(
      problem(422, "validation_error", { field: "name", reason: "duplicate" }),
    );
    expect(call("PATCH /money/categories/2", { emoji: "🦄" })).toEqual(
      problem(422, "validation_error", { field: "emoji", reason: "not_in_set" }),
    );
    expect(call("PATCH /money/categories/99", { hidden: true })).toEqual(problem(404, "not_found", { entity: "category" }));
  });

  it("PUT /money/budget: the month's budget of all expenses, or none", () => {
    const { read, call } = demoApi();
    expect(read<Me>("PUT /money/budget", { amount: "25000.50" }).money_budget).toBe(2_500_050);
    expect(read<Me>("PUT /money/budget", { amount: null }).money_budget).toBeNull();
    expect(read<MoneyMonth>("GET /money")).toMatchObject({ budget: null, left: null, per_day: null });
    expect(call("PUT /money/budget", { amount: "0" })).toEqual(
      problem(422, "validation_error", { field: "amount", reason: "out_of_range" }),
    );
    expect(call("PUT /money/budget", {})).toEqual(problem(422, "validation_error", { field: "amount", detail: "Field required" }));
  });
});

describe("the rates (routers/rates.py)", () => {
  it("GET /rates/all: every currency of the settings, USD, EUR and the user's first, the others by name", () => {
    const { read } = demoApi();
    const rates = read<RatesAll>("GET /rates/all");
    expect(rates.date).toBe("2026-10-07");
    expect(rates.currencies.map((rate) => rate.code).sort()).toEqual(CURRENCY_CODES.filter((code) => code !== "RUB").sort());
    expect(rates.currencies.slice(0, 2).map((rate) => [rate.code, rate.name])).toEqual([["USD", "Доллар США"], ["EUR", "Евро"]]);
    const rest = rates.currencies.slice(2).map((rate) => rate.name);
    expect(rest).toEqual([...rest].sort());
    expect(rates.currencies.every((rate) => rate.value > 0 && Number.isFinite(rate.change))).toBe(true);
    read("PATCH /me", { currency: "KZT" });
    expect(read<RatesAll>("GET /rates/all").currencies.slice(0, 3).map((rate) => rate.code)).toEqual(["USD", "EUR", "KZT"]);
  });

  it("GET /rates/history?code=: thirty days of a currency, the working days, the oldest first", () => {
    const { read, call } = demoApi();
    const history = read<RateHistory>("GET /rates/history?code=EUR");
    expect(history.code).toBe("EUR");
    expect(history.points.length).toBeGreaterThan(18);
    expect(history.points.at(-1)?.day).toBe("2026-10-07");
    const days = history.points.map((point) => point.day);
    expect(days).toEqual([...days].sort());
    expect(days.every((day) => ![0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay()))).toBe(true);
    expect(read<RatesAll>("GET /rates/all").currencies.find((rate) => rate.code === "EUR")?.value).toBe(history.points.at(-1)?.value);
    expect(call("GET /rates/history?code=eur")).toEqual(problem(422, "validation_error", { field: "code" }));
    expect(call("GET /rates/history?code=XAU")).toEqual(problem(404, "not_found", { entity: "currency" }));
    expect(call("GET /rates/history")).toEqual(problem(422, "validation_error", { field: "code", detail: "Field required" }));
  });
});
