import {
  MutationCache, QueryClient, useIsMutating, useMutation, useQuery, useQueryClient,
} from "@tanstack/react-query";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { stateOn, withMark } from "../lib/habits";
import { canShareMessages, haptic, shareMessage } from "../telegram";
import { api, ApiError } from "./client";
import type {
  Agenda, AlertMinutes, City, GroupSearch, Habit, HabitDetail, HabitInput, HabitPatch, Health, Me, MePatch,
  Note, ParsedPhrase, Reminder, ReminderInput, ScheduleState, SharedCard, Today,
} from "./types";

export const keys = {
  me: ["me"],
  today: ["today"],
  notes: ["notes"],
  reminders: ["reminders"],
  habits: ["habits"],
  // Under `habits`: whatever refreshes the list refreshes an open habit too.
  habit: (id: number) => ["habits", id] as const,
  health: ["health"],
  cities: (query: string) => ["cities", query] as const,
  agenda: (from: string, to: string) => ["agenda", from, to] as const,
  schedule: ["schedule"],
  groups: (query: string) => ["groups", query] as const,
  // Under `money`: whatever changes an entry, a category or the budget refreshes them all.
  money: ["money"],
  moneyMonths: ["money", "month"],
  moneyMonth: (month: string) => ["money", "month", month] as const,
  moneyEntry: (id: number) => ["money", "entry", id] as const,
  moneyCategories: ["money", "categories"],
  rates: ["rates"],
  ratesAll: ["rates", "all"],
  rateHistory: (code: string) => ["rates", "history", code] as const,
} as const;

const OWN_TEXT_REASONS = new Set([
  "past", "duplicate", "phrase_not_understood", "repeat_invalid", "needs_time", "schedule", "length",
  "forbidden_host", "unreachable", "too_large", "not_calendar", "source",
]);

/** The key in the `errors` dictionary that explains a failed request. */
export function errorCode(error: unknown): string {
  if (!(error instanceof ApiError)) return "generic";
  if (error.reason && OWN_TEXT_REASONS.has(error.reason)) return error.reason;
  return error.code;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failures, error) =>
          failures < 2 && !(error instanceof ApiError && error.status > 0 && error.status < 500),
      },
      mutations: { retry: false },
    },
    mutationCache: new MutationCache({
      onError: (error) => {
        haptic("error");
        toast({ kind: "error", code: errorCode(error) });
      },
    }),
  });
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => api<Me>("/me") });
export const useToday = () => useQuery({ queryKey: keys.today, queryFn: () => api<Today>("/today") });
export const useNotes = () => useQuery({ queryKey: keys.notes, queryFn: () => api<Note[]>("/notes") });
export const useReminders = () =>
  useQuery({ queryKey: keys.reminders, queryFn: () => api<Reminder[]>("/reminders") });
export const useHabits = () => useQuery({ queryKey: keys.habits, queryFn: () => api<Habit[]>("/habits") });
export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: () => api<Health>("/health"), staleTime: Infinity });

export function useCities(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: keys.cities(trimmed),
    queryFn: ({ signal }) => api<City[]>(`/cities?q=${encodeURIComponent(trimmed)}`, { signal }),
    enabled: trimmed.length >= 2,
    staleTime: 5 * 60_000,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return (list: readonly unknown[]) =>
    Promise.all([
      client.invalidateQueries({ queryKey: list }),
      client.invalidateQueries({ queryKey: keys.today }),
    ]);
}

/**
 * Removes an item from a cached list at once; puts the list back if the request fails — unless
 * it failed with 404: the item is already gone, and putting it back would only flash it until
 * the refetch removes it again. A per-list mutation key lets `onSettled` check whether this is
 * the *last* in-flight delete for that list — refetching while a sibling delete is still in
 * flight would overwrite the optimistic cache with a server list that doesn't yet reflect it,
 * resurrecting the row.
 */
function useOptimisticRemove<T extends { id: number }>(list: readonly unknown[], path: (id: number) => string) {
  const client = useQueryClient();
  const refresh = useRefresh();
  const mutationKey = ["delete", ...list];
  return useMutation({
    mutationKey,
    mutationFn: (id: number) => api<void>(path(id), { method: "DELETE" }),
    onMutate: async (id: number) => {
      await client.cancelQueries({ queryKey: list });
      const previous = client.getQueryData<T[]>(list);
      client.setQueryData<T[]>(list, (items) => items?.filter((item) => item.id !== id));
      return { previous };
    },
    onError: (error, _id, context) => {
      if (!(error instanceof ApiError && error.status === 404)) client.setQueryData(list, context?.previous);
    },
    onSuccess: () => haptic("success"),
    onSettled: () => {
      if (client.isMutating({ mutationKey }) === 1) return refresh(list);
    },
  });
}

export function useCreateNote() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (text: string) => api<Note>("/notes", { method: "POST", body: { text } }),
    onSuccess: () => haptic("success"),
    onSettled: () => refresh(keys.notes),
  });
}

export function useUpdateNote() {
  const client = useQueryClient();
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      api<Note>(`/notes/${id}`, { method: "PATCH", body: { text } }),
    onMutate: async ({ id, text }) => {
      await client.cancelQueries({ queryKey: keys.notes });
      const previous = client.getQueryData<Note[]>(keys.notes);
      client.setQueryData<Note[]>(keys.notes, (notes) =>
        notes?.map((note) => (note.id === id ? { ...note, text } : note)));
      return { previous };
    },
    onError: (_error, _vars, context) => client.setQueryData(keys.notes, context?.previous),
    onSuccess: () => haptic("success"),
    onSettled: () => refresh(keys.notes),
  });
}

export const useDeleteNote = () => useOptimisticRemove<Note>(keys.notes, (id) => `/notes/${id}`);

export const useAgenda = (from: string, to: string, enabled = true) =>
  useQuery({
    queryKey: keys.agenda(from, to),
    queryFn: () => api<Agenda>(`/agenda?from=${from}&to=${to}`),
    enabled,
  });

function useReminderRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.reminders }),
      client.invalidateQueries({ queryKey: ["agenda"] }),
      client.invalidateQueries({ queryKey: keys.today }),
    ]);
}

export function useCreateReminder() {
  const refresh = useReminderRefresh();
  return useMutation({
    mutationFn: (body: ReminderInput) => api<Reminder>("/reminders", { method: "POST", body }),
    onSuccess: () => haptic("success"),
    onSettled: refresh,
  });
}

export function useUpdateReminder() {
  const refresh = useReminderRefresh();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<ReminderInput> }) =>
      api<Reminder>(`/reminders/${id}`, { method: "PATCH", body }),
    onSuccess: () => haptic("success"),
    onSettled: refresh,
  });
}

const DELETE_REMINDER_KEY = ["delete", "reminder"];

/** Removes the reminder from every cached week and from the list at once; puts them back if
 * the request fails (404 excepted: it is gone anyway). */
export function useDeleteReminder() {
  const client = useQueryClient();
  const refresh = useReminderRefresh();
  return useMutation({
    mutationKey: DELETE_REMINDER_KEY,
    mutationFn: (id: number) => api<void>(`/reminders/${id}`, { method: "DELETE" }),
    onMutate: async (id: number) => {
      await Promise.all([
        client.cancelQueries({ queryKey: ["agenda"] }),
        client.cancelQueries({ queryKey: keys.reminders }),
      ]);
      const weeks = client.getQueriesData<Agenda>({ queryKey: ["agenda"] });
      const list = client.getQueryData<Reminder[]>(keys.reminders);
      client.setQueriesData<Agenda>({ queryKey: ["agenda"] }, (agenda) =>
        agenda && {
          days: agenda.days.map((day) => ({
            ...day,
            items: day.items.filter((item) => item.kind !== "reminder" || item.id !== id),
          })),
        });
      client.setQueryData<Reminder[]>(keys.reminders, (items) => items?.filter((item) => item.id !== id));
      return { weeks, list };
    },
    onError: (error, _id, context) => {
      if (error instanceof ApiError && error.status === 404) return;
      for (const [key, data] of context?.weeks ?? []) client.setQueryData(key, data);
      client.setQueryData(keys.reminders, context?.list);
    },
    onSuccess: () => haptic("success"),
    onSettled: () => {
      if (client.isMutating({ mutationKey: DELETE_REMINDER_KEY }) === 1) return refresh();
    },
  });
}

export function useParseReminder() {
  return useMutation({
    mutationFn: (text: string) => api<ParsedPhrase>("/reminders/parse", { method: "POST", body: { text } }),
  });
}

export function useAllowWrite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<Me>("/me/write-access", { method: "POST" }),
    onSuccess: (me) => client.setQueryData(keys.me, me),
  });
}

export const useHabit = (id: number, enabled = true) =>
  useQuery({ queryKey: keys.habit(id), queryFn: () => api<HabitDetail>(`/habits/${id}`), enabled });

export function useCreateHabit() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: HabitInput) => api<Habit>("/habits", { method: "POST", body: input }),
    onSuccess: () => haptic("success"),
    onSettled: () => refresh(keys.habits),
  });
}

export function useUpdateHabit() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: HabitPatch }) =>
      api<Habit>(`/habits/${id}`, { method: "PATCH", body: patch }),
    onSuccess: () => haptic("success"),
    onSettled: () => refresh(keys.habits),
  });
}

export type ShareResult = "shared" | "cancelled" | "sent";

/**
 * Shares a habit's card: in Telegram 8.0+ through a message the bot prepared (the user picks the
 * chat); where the client or the server cannot, the bot sends the card to the user's chat with
 * it instead, to forward from there.
 */
export function useShareHabit() {
  return useMutation({
    mutationFn: async (id: number): Promise<ShareResult> => {
      if (canShareMessages()) {
        try {
          const card = await api<SharedCard>(`/habits/${id}/share`, { method: "POST" });
          return (await shareMessage(card.prepared_id)) ? "shared" : "cancelled";
        } catch (error) {
          // 503: the server cannot prepare shared messages; anything else is the user's to see.
          if (!(error instanceof ApiError && error.status === 503)) throw error;
        }
      }
      await api<void>(`/habits/${id}/card`, { method: "POST" });
      return "sent";
    },
    onSuccess: (result) => {
      if (result !== "cancelled") haptic("success");
    },
  });
}

export const useDeleteHabit = () => useOptimisticRemove<Habit>(keys.habits, (id) => `/habits/${id}`);

const MARK_MUTATION_KEY = ["mark"];

/**
 * Two quick taps (⬜→✅→❌) must not let the first tap's refetch overwrite the second tap's
 * optimistic state, and the two PUTs must commit in the order the user made them. `scope`
 * serialises the actual requests (one at a time, in call order) while `onMutate` still runs
 * immediately for both, so the cache reflects the latest tap right away; the mutation key lets
 * `onSettled` refresh only once — when it is the last mark mutation still in flight.
 * A refused tap puts back only its own habit's earlier mark, and only where its own mark is still
 * the one shown: taps queued behind it are already on screen, and a whole-cache snapshot would wipe them.
 */
export function useSetMark() {
  const client = useQueryClient();
  const refresh = useRefresh();
  const patch = (id: number, done: boolean | null) => (habit: Habit) =>
    habit.id === id ? { ...habit, done_today: done } : habit;
  return useMutation({
    mutationKey: MARK_MUTATION_KEY,
    scope: { id: "habit-mark" },
    mutationFn: ({ id, day, done }: { id: number; day: string; done: boolean | null }) =>
      api<Habit>(`/habits/${id}/marks/${day}`, { method: "PUT", body: { done } }),
    onMutate: async ({ id, done }) => {
      haptic("tap");
      await Promise.all([
        client.cancelQueries({ queryKey: keys.habits }),
        client.cancelQueries({ queryKey: keys.today }),
      ]);
      // The habit as the list shows it, else as Today does. In neither: nothing changes below.
      const inList = client.getQueryData<Habit[]>(keys.habits)?.find((habit) => habit.id === id);
      const inToday = client.getQueryData<Today>(keys.today)?.habits.items.find((habit) => habit.id === id);
      const tapped = inList ?? inToday;
      client.setQueryData<Habit[]>(keys.habits, (items) => items?.map(patch(id, done)));
      client.setQueryData<Today>(keys.today, (data) =>
        data && { ...data, habits: { ...data.habits, items: data.habits.items.map(patch(id, done)) } });
      return tapped && { before: tapped.done_today, done };
    },
    onError: (_error, { id }, tap) => {
      if (!tap) return;
      // A cache is touched only where this tap's mark is still shown; otherwise a later tap owns it.
      const shows = (habit: Habit) => habit.id === id && habit.done_today === tap.done;
      const undo = (habit: Habit) => (shows(habit) ? { ...habit, done_today: tap.before } : habit);
      const list = client.getQueryData<Habit[]>(keys.habits);
      if (list?.some(shows)) client.setQueryData<Habit[]>(keys.habits, list.map(undo));
      const today = client.getQueryData<Today>(keys.today);
      if (today?.habits.items.some(shows)) {
        client.setQueryData<Today>(keys.today, {
          ...today, habits: { ...today.habits, items: today.habits.items.map(undo) },
        });
      }
    },
    onSettled: () => {
      if (client.isMutating({ mutationKey: MARK_MUTATION_KEY }) === 1) return refresh(keys.habits);
    },
  });
}

/** A day's mark in an open habit as the API takes it: true done, false missed, null no mark. */
function markOn(habit: HabitDetail, day: string): boolean | null {
  const state = stateOn(habit.year_from, habit.year, day);
  return state === "done" ? true : state === "missed" ? false : null;
}

/**
 * A mark on any day of an open habit (its month editor): the day changes on screen at once. A
 * refusal puts back only that day, and only while the tap's mark is still the one shown (a later
 * tap on the day owns it by then). It shares useSetMark's scope and key, so marks go to the
 * server one at a time and the list refreshes once, after the last.
 */
export function useMarkDay() {
  const client = useQueryClient();
  const refresh = useRefresh();
  return useMutation({
    mutationKey: MARK_MUTATION_KEY,
    scope: { id: "habit-mark" },
    mutationFn: ({ id, day, done }: { id: number; day: string; done: boolean | null }) =>
      api<Habit>(`/habits/${id}/marks/${day}`, { method: "PUT", body: { done } }),
    onMutate: async ({ id, day, done }) => {
      haptic("tap");
      await client.cancelQueries({ queryKey: keys.habit(id) });
      const cached = client.getQueryData<HabitDetail>(keys.habit(id));
      client.setQueryData<HabitDetail>(keys.habit(id), (habit) =>
        habit && { ...habit, year: withMark(habit.year_from, habit.year, day, done) });
      // A habit that is not cached: nothing changed above, so there is nothing to undo.
      return cached && { before: markOn(cached, day), done };
    },
    onError: (_error, { id, day }, tap) => {
      const habit = client.getQueryData<HabitDetail>(keys.habit(id));
      if (tap && habit && markOn(habit, day) === tap.done) {
        client.setQueryData<HabitDetail>(keys.habit(id), {
          ...habit, year: withMark(habit.year_from, habit.year, day, tap.before),
        });
      }
    },
    onSettled: () => {
      if (client.isMutating({ mutationKey: MARK_MUTATION_KEY }) === 1) return refresh(keys.habits);
    },
  });
}

const ME_UPDATE_KEY = ["me-update"];

/**
 * Settings change on screen at once and are rolled back if the server refuses. `scope` sends
 * the PATCHes one at a time in the order they were made; an answer is written to the cache only
 * by the last one in flight, as an earlier answer would undo the later changes on screen.
 */
export function useUpdateMe() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: ME_UPDATE_KEY,
    scope: { id: "me-update" },
    mutationFn: (body: MePatch) => api<Me>("/me", { method: "PATCH", body }),
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: keys.me });
      const previous = client.getQueryData<Me>(keys.me);
      // Only the setting: which language "auto" means is the server's answer to give.
      client.setQueryData<Me>(keys.me, (me) => me && {
        ...me,
        language_setting: body.language ?? me.language_setting,
        currency: body.currency ?? me.currency,
        morning: {
          enabled: body.morning_enabled ?? me.morning.enabled,
          time: body.morning_time ?? me.morning.time,
        },
      });
      return { previous };
    },
    onError: (_error, _body, context) => client.setQueryData(keys.me, context?.previous),
    onSuccess: (me) => {
      if (client.isMutating({ mutationKey: ME_UPDATE_KEY }) === 1) client.setQueryData(keys.me, me);
      haptic("success");
      // The server words categories and currencies in the user's language, amounts in their currency.
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.today }),
        client.invalidateQueries({ queryKey: keys.money }),
        client.invalidateQueries({ queryKey: keys.rates }),
      ]);
    },
    onSettled: (_me, error) => {
      // After a refusal only the server knows which of several quick changes were kept.
      if (error && client.isMutating({ mutationKey: ME_UPDATE_KEY }) === 1) {
        return client.invalidateQueries({ queryKey: keys.me });
      }
    },
  });
}

export function useSetCity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (city: City) =>
      api<Me>("/me/city", {
        method: "PUT",
        body: { name: city.name, lat: city.lat, lon: city.lon, timezone: city.timezone },
      }),
    onSuccess: (me) => {
      client.setQueryData(keys.me, me);
      haptic("success");
      // Habits' `done_today` is computed against the city's local date, so a city change can
      // shift which day "today" is for them too. Lessons and reminders are shown in the city's zone.
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.today }),
        client.invalidateQueries({ queryKey: ["agenda"] }),
        client.invalidateQueries({ queryKey: keys.reminders }),
        client.invalidateQueries({ queryKey: keys.habits }),
      ]);
    },
  });
}

export const useSchedule = () =>
  useQuery({ queryKey: keys.schedule, queryFn: () => api<ScheduleState>("/schedule") });

export function useGroups(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: keys.groups(trimmed),
    queryFn: ({ signal }) =>
      api<GroupSearch>(`/schedule/groups?q=${encodeURIComponent(trimmed)}`, { signal }),
    enabled: trimmed.length >= 2,
    staleTime: 5 * 60_000,
  });
}

/** A changed timetable changes the calendar and «Сегодня» too. */
function useScheduleSaved() {
  const client = useQueryClient();
  return (state: ScheduleState) => {
    client.setQueryData(keys.schedule, state);
    return Promise.all([
      client.invalidateQueries({ queryKey: ["agenda"] }),
      client.invalidateQueries({ queryKey: keys.today }),
    ]);
  };
}

/** The source is gone already (disconnected from the bot or another device): show that at once. */
function forgetOnGone(saved: ReturnType<typeof useScheduleSaved>) {
  return (error: Error) =>
    error instanceof ApiError && error.status === 404 ? saved({ source: null }) : undefined;
}

// One schedule change at a time: a late answer must never overwrite a newer state.
export function useConnectSchedule() {
  const saved = useScheduleSaved();
  return useMutation({
    scope: { id: "schedule" },
    mutationFn: (body: { mirea_id: number; url?: never } | { url: string; mirea_id?: never }) =>
      api<ScheduleState>("/schedule", { method: "PUT", body }),
    onSuccess: (state) => {
      haptic("success");
      return saved(state);
    },
  });
}

export function useUploadSchedule() {
  const saved = useScheduleSaved();
  return useMutation({
    scope: { id: "schedule" },
    mutationFn: (file: File) =>
      api<ScheduleState>(`/schedule/file?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file }),
    onSuccess: (state) => {
      haptic("success");
      return saved(state);
    },
    // No onError: POST /schedule/file has no 404 of its own, so one (a proxy's, say) must not
    // wipe the source the app knows.
  });
}

const REFRESH_SCHEDULE_KEY = ["schedule-refresh"];

/**
 * The result is told by the mutation itself, not by the card that started it: «Сменить источник»
 * → «Отмена» during a refresh draws a new source card, and callbacks the old one gave `mutate()`
 * would never run.
 */
export function useRefreshSchedule() {
  const t = useT();
  const saved = useScheduleSaved();
  return useMutation({
    mutationKey: REFRESH_SCHEDULE_KEY,
    scope: { id: "schedule" },
    mutationFn: () => api<ScheduleState>("/schedule/refresh", { method: "POST" }),
    onSuccess: async (state) => {
      await saved(state);
      const error = state.source?.error;
      if (error) toast({ kind: "error", code: error });
      else toast({ kind: "success", text: t.schedule.refreshed });
    },
    onError: forgetOnGone(saved),
  });
}

/** Whether a refresh is running — started from this source card or from one it replaced. */
export const useScheduleRefreshing = () => useIsMutating({ mutationKey: REFRESH_SCHEDULE_KEY }) > 0;

export function useScheduleAlerts() {
  const client = useQueryClient();
  const saved = useScheduleSaved();
  return useMutation({
    scope: { id: "schedule" },
    mutationFn: (minutes: AlertMinutes | null) =>
      api<ScheduleState>("/schedule", { method: "PATCH", body: { lesson_reminder_minutes: minutes } }),
    onSuccess: (state) => {
      haptic("select");
      client.setQueryData(keys.schedule, state);
    },
    onError: forgetOnGone(saved),
  });
}

export function useDisconnectSchedule() {
  const saved = useScheduleSaved();
  return useMutation({
    scope: { id: "schedule" },
    mutationFn: () => api<void>("/schedule", { method: "DELETE" }),
    onSuccess: () => {
      haptic("success");
      return saved({ source: null });
    },
    onError: forgetOnGone(saved),
  });
}
