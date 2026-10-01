import {
  MutationCache, QueryClient, useMutation, useQuery, useQueryClient,
} from "@tanstack/react-query";
import { toast } from "../components/toastStore";
import { haptic } from "../telegram";
import { api, ApiError } from "./client";
import type {
  Agenda, AlertMinutes, City, GroupSearch, Habit, Health, Me, Note, ParsedPhrase, Reminder, ReminderInput,
  ScheduleState, Today,
} from "./types";

export const keys = {
  me: ["me"],
  today: ["today"],
  notes: ["notes"],
  reminders: ["reminders"],
  habits: ["habits"],
  health: ["health"],
  cities: (query: string) => ["cities", query] as const,
  agenda: (from: string, to: string) => ["agenda", from, to] as const,
  schedule: ["schedule"],
  groups: (query: string) => ["groups", query] as const,
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

export function useCreateHabit() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (name: string) => api<Habit>("/habits", { method: "POST", body: { name } }),
    onSuccess: () => haptic("success"),
    onSettled: () => refresh(keys.habits),
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
      const previous = {
        habits: client.getQueryData<Habit[]>(keys.habits),
        today: client.getQueryData<Today>(keys.today),
      };
      client.setQueryData<Habit[]>(keys.habits, (items) => items?.map(patch(id, done)));
      client.setQueryData<Today>(keys.today, (data) =>
        data && { ...data, habits: { ...data.habits, items: data.habits.items.map(patch(id, done)) } });
      return previous;
    },
    onError: (_error, _vars, previous) => {
      client.setQueryData(keys.habits, previous?.habits);
      client.setQueryData(keys.today, previous?.today);
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
    mutationFn: (body: { language?: "auto" | "ru" | "en"; morning_enabled?: boolean; morning_time?: string }) =>
      api<Me>("/me", { method: "PATCH", body }),
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: keys.me });
      const previous = client.getQueryData<Me>(keys.me);
      // Only the setting: which language "auto" means is the server's answer to give.
      client.setQueryData<Me>(keys.me, (me) => me && {
        ...me,
        language_setting: body.language ?? me.language_setting,
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
      return client.invalidateQueries({ queryKey: keys.today });
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
    onError: forgetOnGone(saved),
  });
}

export function useRefreshSchedule() {
  const saved = useScheduleSaved();
  return useMutation({
    scope: { id: "schedule" },
    mutationFn: () => api<ScheduleState>("/schedule/refresh", { method: "POST" }),
    onSuccess: (state) => saved(state),
    onError: forgetOnGone(saved),
  });
}

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
