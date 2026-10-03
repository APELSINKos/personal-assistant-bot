import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "../components/toastStore";
import { useLang, useT } from "../i18n";
import { alertText, DEFAULT_CURRENCY } from "../lib/money";
import { haptic } from "../telegram";
import { api, ApiError } from "./client";
import { keys } from "./queries";
import type {
  Me, MoneyCategory, MoneyCategoryInput, MoneyCategoryPatch, MoneyEntry, MoneyEntryInput, MoneyEntrySaved,
  MoneyMonth, RateHistory, RatesAll,
} from "./types";

/** An entry changes its month's totals and the «Сегодня» card. */
function refresh(client: QueryClient) {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.money }),
    client.invalidateQueries({ queryKey: keys.today }),
  ]);
}

/** A month's totals, categories and entries; `month` is «2026-10». */
export const useMoneyMonth = (month: string) =>
  useQuery({ queryKey: keys.moneyMonth(month), queryFn: () => api<MoneyMonth>(`/money?month=${month}`) });

export const useMoneyEntry = (id: number) =>
  useQuery({ queryKey: keys.moneyEntry(id), queryFn: () => api<MoneyEntry>(`/money/entries/${id}`) });

export const useMoneyCategories = () =>
  useQuery({ queryKey: keys.moneyCategories, queryFn: () => api<MoneyCategory[]>("/money/categories") });

// The bank sets its rates once a day, and the server keeps them for half an hour.
export const useRatesAll = () =>
  useQuery({ queryKey: keys.ratesAll, queryFn: () => api<RatesAll>("/rates/all"), staleTime: 10 * 60_000 });

export const useRateHistory = (code: string) =>
  useQuery({
    queryKey: keys.rateHistory(code),
    queryFn: () => api<RateHistory>(`/rates/history?code=${encodeURIComponent(code)}`),
    staleTime: 60 * 60_000,
  });

/**
 * A new entry with all its fields, or a change of an entry: only what changed, since a day left
 * as it was may already be out of the window a new day has to fit in.
 */
type EntrySave = { id?: undefined; entry: MoneyEntryInput } | { id: number; entry: Partial<MoneyEntryInput> };

/** Notes a new entry or changes one. The budget warnings it set off come up as toasts, worded as the bot's. */
export function useSaveEntry() {
  const client = useQueryClient();
  const t = useT();
  const lang = useLang();
  return useMutation({
    mutationFn: ({ id, entry }: EntrySave) =>
      id === undefined
        ? api<MoneyEntrySaved>("/money/entries", { method: "POST", body: entry })
        : api<MoneyEntrySaved>(`/money/entries/${id}`, { method: "PATCH", body: entry }),
    onSuccess: (saved) => {
      haptic(saved.alerts.length ? "warning" : "success");
      client.setQueryData(keys.moneyEntry(saved.entry.id), saved.entry);
      const currency = client.getQueryData<Me>(keys.me)?.currency ?? DEFAULT_CURRENCY;
      for (const alert of saved.alerts) {
        toast({ kind: "warning", text: alertText(alert, saved.entry.day, currency, lang, t) });
      }
    },
    onSettled: () => refresh(client),
  });
}

const DELETE_ENTRY_KEY = ["delete", "money-entry"];

/**
 * Takes an entry out of every cached month at once (the totals follow with the refetch) and puts
 * the months back if the request fails — unless with 404: the entry is already gone. Only the
 * last delete in flight refetches, so a quicker one does not bring back a row still being deleted.
 */
export function useDeleteEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: DELETE_ENTRY_KEY,
    mutationFn: (id: number) => api<void>(`/money/entries/${id}`, { method: "DELETE" }),
    onMutate: async (id: number) => {
      await client.cancelQueries({ queryKey: keys.money });
      const previous = client.getQueriesData<MoneyMonth>({ queryKey: keys.moneyMonths });
      client.setQueriesData<MoneyMonth>({ queryKey: keys.moneyMonths }, (month) =>
        month && { ...month, entries: month.entries.filter((entry) => entry.id !== id) });
      return { previous };
    },
    onError: (error, _id, context) => {
      if (error instanceof ApiError && error.status === 404) return;
      for (const [key, month] of context?.previous ?? []) client.setQueryData(key, month);
    },
    onSuccess: (_data, id) => {
      haptic("success");
      client.removeQueries({ queryKey: keys.moneyEntry(id) });
    },
    onSettled: () => {
      if (client.isMutating({ mutationKey: DELETE_ENTRY_KEY }) === 1) return refresh(client);
    },
  });
}

export function useCreateCategory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (category: MoneyCategoryInput) =>
      api<MoneyCategory>("/money/categories", { method: "POST", body: category }),
    onSuccess: () => haptic("success"),
    onSettled: () => client.invalidateQueries({ queryKey: keys.money }),
  });
}

/** Renames a category, changes its emoji, hides or shows it, sets or removes (`budget: null`) its budget. */
export function useUpdateCategory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: MoneyCategoryPatch }) =>
      api<MoneyCategory>(`/money/categories/${id}`, { method: "PATCH", body: patch }),
    onSuccess: () => haptic("success"),
    onSettled: () => client.invalidateQueries({ queryKey: keys.money }),
  });
}

/** The total budget of a month: a decimal with a point, or null to remove it. */
export function useSetBudget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (amount: string | null) => api<Me>("/money/budget", { method: "PUT", body: { amount } }),
    onSuccess: (me) => {
      client.setQueryData(keys.me, me);
      haptic("success");
    },
    onSettled: () => refresh(client),
  });
}
