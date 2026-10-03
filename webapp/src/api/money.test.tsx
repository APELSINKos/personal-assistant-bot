import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "../components/toastStore";
import { LangProvider } from "../i18n";
import { installTelegram } from "../test/fakeTelegram";
import { me, moneyCategories, moneyMonth } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import {
  useDeleteEntry, useMoneyEntry, useMoneyMonth, useRateHistory, useRatesAll, useSaveEntry, useSetBudget,
  useUpdateCategory,
} from "./money";
import { createQueryClient, keys, useUpdateMe } from "./queries";
import type { Me, MoneyEntrySaved, MoneyMonth } from "./types";

beforeEach(() => {
  installTelegram();
});

function wrapperFor(client: ReturnType<typeof createQueryClient>) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <LangProvider lang="ru">{children}</LangProvider>
      </QueryClientProvider>
    );
  };
}

const ENTRY = { amount: "430.50", category_id: 2, note: "кофе", day: "2026-09-28" };
const SAVED: MoneyEntrySaved = {
  entry: { id: 24, amount: 43050, category_id: 2, note: "кофе", day: "2026-09-28" },
  alerts: [
    { category_id: null, emoji: null, name: null, threshold: 80, spent: 2410000, budget: 3000000 },
    { category_id: 2, emoji: "☕", name: "Кафе", threshold: 100, spent: 530000, budget: 500000 },
  ],
};

function entryIds(client: ReturnType<typeof createQueryClient>, month: string) {
  return client.getQueryData<MoneyMonth>(keys.moneyMonth(month))?.entries.map((entry) => entry.id);
}

describe("money", () => {
  it("fetches a month and one entry", async () => {
    const { calls } = mockApi({ "GET /money?month=2026-09": moneyMonth, "GET /money/entries/24": SAVED.entry });
    const client = createQueryClient();
    const month = renderHook(() => useMoneyMonth("2026-09"), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(month.result.current.data?.spent).toBe(1698050));
    const entry = renderHook(() => useMoneyEntry(24), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(entry.result.current.data?.note).toBe("кофе"));
    expect(calls.map((call) => call.path)).toEqual(["/money?month=2026-09", "/money/entries/24"]);
  });

  it("notes an entry, refreshes the money and today, and warns about the budgets", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "POST /money/entries": { status: 201, body: SAVED } });
    const client = createQueryClient();
    client.setQueryData(keys.me, me);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const toasts = renderHook(() => useToasts());
    const { result } = renderHook(() => useSaveEntry(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ entry: ENTRY }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "POST", path: "/money/entries", body: ENTRY });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["money"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["today"] });
    expect(app.HapticFeedback?.notificationOccurred).toHaveBeenCalledWith("warning");
    expect(toasts.result.current.map((item) => [item.kind, item.text])).toEqual([
      ["warning", "⚠️ Потрачено 80\u00a0% бюджета на сентябрь: 24\u00a0100\u00a0₽ из 30\u00a0000\u00a0₽"],
      ["warning", "🚨 Бюджет «☕ Кафе» на сентябрь закончился: 5\u00a0300\u00a0₽ из 5\u00a0000\u00a0₽"],
    ]);
  });

  it("changes an entry by its id and keeps the answer for its form", async () => {
    const { calls } = mockApi({ "PATCH /money/entries/24": { ...SAVED, alerts: [] } });
    const client = createQueryClient();
    const { result } = renderHook(() => useSaveEntry(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ id: 24, entry: ENTRY }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "PATCH", path: "/money/entries/24", body: ENTRY });
    expect(client.getQueryData(keys.moneyEntry(24))).toEqual(SAVED.entry);
  });

  it("takes a deleted entry out of every cached month at once", async () => {
    let answer: (reply: { status: number }) => void = () => undefined;
    const { calls } = mockApi({ "DELETE /money/entries/24": () => new Promise((resolve) => { answer = resolve; }) });
    const client = createQueryClient();
    client.setQueryData(keys.moneyMonth("2026-09"), moneyMonth);
    client.setQueryData(keys.moneyMonth("2026-08"), { ...moneyMonth, month: "2026-08", entries: [] });
    const { result } = renderHook(() => useDeleteEntry(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(24));
    await waitFor(() => expect(entryIds(client, "2026-09")).toEqual([23, 22, 21, 20]));
    expect(entryIds(client, "2026-08")).toEqual([]);
    act(() => answer({ status: 204 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/money/entries/24" });
    expect(entryIds(client, "2026-09")).toEqual([23, 22, 21, 20]);
  });

  it("puts a deleted entry back when the server refuses, but not one already gone", async () => {
    mockApi({
      "DELETE /money/entries/24": { status: 500, body: { status: 500, code: "internal_error" } },
      "DELETE /money/entries/23": { status: 404, body: { status: 404, code: "not_found" } },
    });
    const client = createQueryClient();
    client.setQueryData(keys.moneyMonth("2026-09"), moneyMonth);
    const { result } = renderHook(() => useDeleteEntry(), { wrapper: wrapperFor(client) });
    const settled = () => client.getMutationCache().getAll().map((mutation) => mutation.state.status);
    act(() => result.current.mutate(24));
    await waitFor(() => expect(settled()).toEqual(["error"]));
    expect(entryIds(client, "2026-09")).toEqual([24, 23, 22, 21, 20]);
    act(() => result.current.mutate(23));
    await waitFor(() => expect(settled()).toEqual(["error", "error"]));
    expect(entryIds(client, "2026-09")).toEqual([24, 22, 21, 20]);
  });

  it("sets the total budget and keeps the new me", async () => {
    const { calls } = mockApi({ "PUT /money/budget": { ...me, money_budget: 3000000 } });
    const client = createQueryClient();
    client.setQueryData(keys.me, me);
    const { result } = renderHook(() => useSetBudget(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate("30000"));
    await waitFor(() => expect(client.getQueryData<Me>(keys.me)?.money_budget).toBe(3000000));
    expect(calls[0]).toMatchObject({ method: "PUT", path: "/money/budget", body: { amount: "30000" } });
  });

  it("removes a category's budget with null", async () => {
    const { calls } = mockApi({ "PATCH /money/categories/2": { ...moneyCategories[1], budget: null } });
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ id: 2, patch: { budget: null } }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "PATCH", path: "/money/categories/2", body: { budget: null } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["money"] });
  });
});

describe("rates", () => {
  it("fetches the day's rates and a currency's 30 days", async () => {
    const { calls } = mockApi({
      "GET /rates/all": {
        date: "2026-09-28", currencies: [{ code: "USD", name: "Доллар США", value: 84.2, change: -0.3 }],
      },
      "GET /rates/history?code=USD": { code: "USD", points: [{ day: "2026-09-26", value: 84.2 }] },
    });
    const client = createQueryClient();
    const all = renderHook(() => useRatesAll(), { wrapper: wrapperFor(client) });
    const history = renderHook(() => useRateHistory("USD"), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(all.result.current.data?.currencies[0]?.code).toBe("USD"));
    await waitFor(() => expect(history.result.current.data?.points).toHaveLength(1));
    expect(calls.map((call) => call.path).sort()).toEqual(["/rates/all", "/rates/history?code=USD"]);
  });

  it("shows a new currency at once and refreshes what the server words in it", async () => {
    let answer: (reply: { body: Me }) => void = () => undefined;
    mockApi({ "PATCH /me": () => new Promise((resolve) => { answer = resolve; }) });
    const client = createQueryClient();
    client.setQueryData(keys.me, me);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUpdateMe(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ currency: "USD" }));
    await waitFor(() => expect(client.getQueryData<Me>(keys.me)?.currency).toBe("USD"));
    act(() => answer({ body: { ...me, currency: "USD" } }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["money"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["rates"] });
  });
});
