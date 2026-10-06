import {
  MutationCache, QueryClient, useIsMutating, useMutation, useQuery, useQueryClient,
} from "@tanstack/react-query";
import { toast } from "../components/toastStore";
import { hasErrorText, useT } from "../i18n";
import { stateOn, withMark } from "../lib/habits";
import { canShareMessages, haptic, shareMessage } from "../telegram";
import { api, ApiError } from "./client";
import type {
  Agenda, AlertMinutes, City, Forecast, GroupSearch, Habit, HabitDetail, HabitInput, HabitPatch, Health, Me,
  MePatch, Note, NoteInput, NoteItem, ParsedPhrase, Reminder, ReminderInput, ScheduleState, SharedCard, Today,
  WeatherCity,
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
  // Under `weather`: a new home city changes the home forecast and may leave the extra cities.
  weather: ["weather"],
  forecast: (city: number) => ["weather", "forecast", city] as const,
  weatherCities: ["weather", "cities"],
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
  if (error.code === "limit_reached") {
    // The limit's own words where the dictionary has them: «В заметке уже 20 пунктов».
    const own = `limit_${String(error.details.entity)}`;
    return hasErrorText(own) ? own : "limit_reached";
  }
  if (error.reason === "duplicate" && error.details.field === "city") return "duplicate_city";
  if (error.reason && OWN_TEXT_REASONS.has(error.reason)) return error.reason;
  return error.code;
}

/** A 404: what the request was about is gone already — deleted in the bot or on another device. */
function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** The meta of a request that answers its own 404, so the usual toast stays away. */
const OWN_NOT_FOUND = { ownNotFound: true };

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
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.ownNotFound === true && isGone(error)) return;
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

/** A city's forecast: 0 is the home city, any other id one of the extra cities. */
export const useForecast = (city: number) =>
  useQuery({
    queryKey: keys.forecast(city),
    queryFn: () => api<Forecast>(city ? `/weather?city=${city}` : "/weather"),
  });

export const useWeatherCities = () =>
  useQuery({ queryKey: keys.weatherCities, queryFn: () => api<WeatherCity[]>("/me/cities") });

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

// Every change of the notes — a note created or deleted, its text, its pin, its items — has a key
// under this one, and only the last of them in flight asks for the notes again: a list fetched
// between two would bring back on screen what the later one is still changing.
const NOTE_CHANGE = ["note-change"];
const CREATE_CHANGE = [...NOTE_CHANGE, "create"];
const DELETE_CHANGE = [...NOTE_CHANGE, "delete"];
const TEXT_CHANGE = [...NOTE_CHANGE, "text"];
const PIN_CHANGE = [...NOTE_CHANGE, "pin"];
const ITEM_CHANGE = [...NOTE_CHANGE, "items"];
const ITEMS_SCOPE = { id: "note-items" };

/** After a change of the notes: the notes and «Сегодня» again, once the last change is done. */
function useNoteChanged() {
  const client = useQueryClient();
  const refresh = useRefresh();
  return () => {
    if (client.isMutating({ mutationKey: NOTE_CHANGE }) === 1) return refresh(keys.notes);
  };
}

function noteIn(client: QueryClient, id: number): Note | undefined {
  return client.getQueryData<Note[]>(keys.notes)?.find((note) => note.id === id);
}

function itemIn(client: QueryClient, note: number, id: number): NoteItem | undefined {
  return noteIn(client, note)?.items.find((item) => item.id === id);
}

function changeNote(client: QueryClient, id: number, change: (note: Note) => Note): void {
  client.setQueryData<Note[]>(keys.notes, (notes) => notes?.map((note) => (note.id === id ? change(note) : note)));
}

/**
 * Shows a note the list lacks: before the note whose index `place` finds in the list, or last when
 * it finds none (-1). A note the list has already (a fetch brought it) stays where it is, and a
 * list that is not cached stays so.
 */
function showNote(client: QueryClient, shown: Note, place: (notes: Note[]) => number): void {
  client.setQueryData<Note[]>(keys.notes, (notes) => {
    if (!notes || notes.some((note) => note.id === shown.id)) return notes;
    const index = place(notes);
    return index === -1 ? [...notes, shown] : [...notes.slice(0, index), shown, ...notes.slice(index)];
  });
}

/**
 * Changes the items of a cached note, and «Сегодня»'s count of them where the note is pinned. Where
 * the list or the note is not cached, nothing changes: the refetch after the request shows it.
 */
function changeItems(client: QueryClient, id: number, change: (items: NoteItem[]) => NoteItem[]): void {
  const note = noteIn(client, id);
  if (!note) return;
  const items = change(note.items);
  if (items === note.items) return;
  changeNote(client, id, (shown) => ({ ...shown, items }));
  const done = items.filter((item) => item.done).length;
  client.setQueryData<Today>(keys.today, (today) =>
    today?.pinned_notes.some((pinned) => pinned.id === id)
      ? {
        ...today,
        pinned_notes: today.pinned_notes.map((pinned) =>
          pinned.id === id ? { ...pinned, done, total: items.length } : pinned),
      }
      : today);
}

/** Puts back the items a refused request took away — those still away, in their order. */
function putBack(client: QueryClient, note: number, removed: readonly NoteItem[]): void {
  changeItems(client, note, (items) => {
    const missing = removed.filter((item) => !items.some((shown) => shown.id === item.id));
    return missing.length ? [...items, ...missing].sort((a, b) => a.id - b.id) : items;
  });
}

/** No fetch of the notes or of «Сегодня» may land over a change the screen shows already. */
function holdNotes(client: QueryClient) {
  return Promise.all([
    client.cancelQueries({ queryKey: keys.notes }),
    client.cancelQueries({ queryKey: keys.today }),
  ]);
}

/** The answer to an item request that found its item or note gone. */
function useGoneToast() {
  const t = useT();
  return () => {
    haptic("error");
    toast({ kind: "error", text: t.notes.gone });
  };
}

/**
 * A new note: a checklist with its items, pinned at once if asked — all of it or nothing. It shows
 * once the server has it, where the list will have it: a pinned one on top, any other first after
 * the pinned ones, as the newest.
 */
export function useCreateNote() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  return useMutation({
    mutationKey: CREATE_CHANGE,
    mutationFn: (note: NoteInput) => api<Note>("/notes", { method: "POST", body: note }),
    onSuccess: async (created) => {
      haptic("success");
      await client.cancelQueries({ queryKey: keys.notes });
      showNote(client, created, (notes) => (created.pinned ? 0 : notes.findIndex((note) => !note.pinned)));
    },
    onSettled: changed,
  });
}

/**
 * Deletes a note: it leaves the list at once. A refusal puts back only this note, in its place —
 * before the first of the notes that followed it still shown — so what changed meanwhile stays;
 * a 404 puts back nothing, as the note is gone either way.
 */
export function useDeleteNote() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  return useMutation({
    mutationKey: DELETE_CHANGE,
    mutationFn: (id: number) => api<void>(`/notes/${id}`, { method: "DELETE" }),
    onMutate: async (id: number) => {
      await client.cancelQueries({ queryKey: keys.notes });
      const notes = client.getQueryData<Note[]>(keys.notes) ?? [];
      const index = notes.findIndex((note) => note.id === id);
      client.setQueryData<Note[]>(keys.notes, (shown) => shown?.filter((note) => note.id !== id));
      // A note not shown has nothing to put back; a shown one, its place: the notes after it now.
      const removed = notes[index];
      return removed && { removed, after: notes.slice(index + 1).map((note) => note.id) };
    },
    onError: (error, _id, context) => {
      if (!context || isGone(error)) return;
      showNote(client, context.removed, (notes) => notes.findIndex((note) => context.after.includes(note.id)));
    },
    onSuccess: () => haptic("success"),
    onSettled: changed,
  });
}

/** Saves a note's text; its pin and its items are requests of their own. */
export function useUpdateNote() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  return useMutation({
    mutationKey: TEXT_CHANGE,
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      api<Note>(`/notes/${id}`, { method: "PATCH", body: { text } }),
    onMutate: async ({ id, text }) => {
      await client.cancelQueries({ queryKey: keys.notes });
      const before = noteIn(client, id)?.text;
      changeNote(client, id, (note) => ({ ...note, text }));
      return before === undefined ? undefined : { before, text };
    },
    // Only the text, and only while it is this save's: an item checked meanwhile stays checked.
    onError: (_error, { id }, saved) => {
      if (saved) changeNote(client, id, (note) => (note.text === saved.text ? { ...note, text: saved.before } : note));
    },
    onSuccess: () => haptic("success"),
    onSettled: changed,
  });
}

/**
 * Pins or unpins a saved note: the pin changes on screen at once, and a refusal (409 at five
 * pinned notes) puts it back — only while this tap's pin is the one shown, as with marks. Taps go
 * to the server one at a time, in their order.
 */
export function usePinNote() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  return useMutation({
    mutationKey: PIN_CHANGE,
    scope: { id: "note-pin" },
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) =>
      api<Note>(`/notes/${id}`, { method: "PATCH", body: { pinned } }),
    onMutate: async ({ id, pinned }) => {
      haptic("tap");
      await client.cancelQueries({ queryKey: keys.notes });
      const before = noteIn(client, id)?.pinned;
      changeNote(client, id, (note) => ({ ...note, pinned }));
      return before === undefined ? undefined : { before, pinned };
    },
    onError: (_error, { id }, tap) => {
      if (tap) changeNote(client, id, (note) => (note.pinned === tap.pinned ? { ...note, pinned: tap.before } : note));
    },
    onSettled: changed,
  });
}

// The items of a checklist go as useSetMark's marks do: the screen changes at once, the requests
// reach the server one at a time in the order they were made, the notes and «Сегодня» are asked
// for again once, after the last. A refusal takes back only its own item, and only while the
// screen shows what this request did; a 404 (the item or the note is gone) takes back nothing.

/**
 * Adds an item to a saved note. It shows once the server has given it an id: with no temporary
 * ids, nothing can check an item that does not exist yet. Items added in a row go in their order.
 */
export function useAddItem() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  const gone = useGoneToast();
  return useMutation({
    mutationKey: ITEM_CHANGE,
    scope: ITEMS_SCOPE,
    meta: OWN_NOT_FOUND,
    mutationFn: ({ note, text }: { note: number; text: string }) =>
      api<NoteItem>(`/notes/${note}/items`, { method: "POST", body: { text } }),
    onSuccess: async (item, { note }) => {
      haptic("success");
      await holdNotes(client);
      changeItems(client, note, (items) => (items.some((shown) => shown.id === item.id) ? items : [...items, item]));
    },
    onError: (error) => {
      if (isGone(error)) gone();
    },
    onSettled: changed,
  });
}

/**
 * Checks or unchecks an item. It sets the state rather than switching it, so a tap on a screen
 * that is behind never undoes what another device did.
 */
export function useSetItem() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  const gone = useGoneToast();
  const mark = (id: number, done: boolean) => (items: NoteItem[]) =>
    items.map((item) => (item.id === id ? { ...item, done } : item));
  return useMutation({
    mutationKey: ITEM_CHANGE,
    scope: ITEMS_SCOPE,
    meta: OWN_NOT_FOUND,
    mutationFn: ({ note, id, done }: { note: number; id: number; done: boolean }) =>
      api<NoteItem>(`/notes/${note}/items/${id}`, { method: "PATCH", body: { done } }),
    onMutate: async ({ note, id, done }) => {
      haptic("tap");
      await holdNotes(client);
      const before = itemIn(client, note, id)?.done;
      changeItems(client, note, mark(id, done));
      return before === undefined ? undefined : { before, done };
    },
    onError: (error, { note, id }, tap) => {
      if (isGone(error)) return gone();
      // A later tap on the item owns it once its state is the one shown.
      if (tap && itemIn(client, note, id)?.done === tap.done) changeItems(client, note, mark(id, tap.before));
    },
    onSettled: changed,
  });
}

/** Deletes an item without asking; a 404 says nothing, as the item is gone either way. */
export function useDeleteItem() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  return useMutation({
    mutationKey: ITEM_CHANGE,
    scope: ITEMS_SCOPE,
    meta: OWN_NOT_FOUND,
    mutationFn: ({ note, id }: { note: number; id: number }) =>
      api<void>(`/notes/${note}/items/${id}`, { method: "DELETE" }),
    onMutate: async ({ note, id }) => {
      await holdNotes(client);
      const item = itemIn(client, note, id);
      changeItems(client, note, (items) => items.filter((shown) => shown.id !== id));
      return { removed: item ? [item] : [] };
    },
    onError: (error, { note }, context) => {
      if (!isGone(error)) putBack(client, note, context?.removed ?? []);
    },
    onSuccess: () => haptic("success"),
    onSettled: changed,
  });
}

/** «Убрать отмеченные»: the checked items of a note go, without asking. */
export function useClearDone() {
  const client = useQueryClient();
  const changed = useNoteChanged();
  const gone = useGoneToast();
  return useMutation({
    mutationKey: ITEM_CHANGE,
    scope: ITEMS_SCOPE,
    meta: OWN_NOT_FOUND,
    mutationFn: (note: number) => api<void>(`/notes/${note}/items?done=true`, { method: "DELETE" }),
    onMutate: async (note: number) => {
      await holdNotes(client);
      const removed = noteIn(client, note)?.items.filter((item) => item.done) ?? [];
      changeItems(client, note, (items) => items.filter((item) => !item.done));
      return { removed };
    },
    onError: (error, note, context) => {
      if (isGone(error)) return gone();
      putBack(client, note, context?.removed ?? []);
    },
    onSuccess: () => haptic("success"),
    onSettled: changed,
  });
}

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
        // By the found place's GeoNames id (or its coordinates) the new home leaves the extra cities.
        body: { name: city.name, lat: city.lat, lon: city.lon, timezone: city.timezone, geo_id: city.geo_id ?? null },
      }),
    onSuccess: (me) => {
      client.setQueryData(keys.me, me);
      haptic("success");
      // Habits' `done_today` and the money month's days are computed against the city's local
      // date, so a city change can shift which day "today" is for them too. Lessons and reminders
      // are shown in the city's zone. The home forecast is another city's now.
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.today }),
        client.invalidateQueries({ queryKey: ["agenda"] }),
        client.invalidateQueries({ queryKey: keys.reminders }),
        client.invalidateQueries({ queryKey: keys.habits }),
        client.invalidateQueries({ queryKey: keys.money }),
        client.invalidateQueries({ queryKey: keys.weather }),
      ]);
    },
  });
}

// Adding and deleting the extra cities: one request at a time, in the order they were made, and
// the list is asked for again only after the last — before, it could bring back a city being deleted.
const CITY_CHANGE = ["city-change"];
const CITIES_SCOPE = { id: "cities" };

function useCitiesChanged() {
  const client = useQueryClient();
  return () => {
    if (client.isMutating({ mutationKey: CITY_CHANGE }) === 1) {
      return client.invalidateQueries({ queryKey: keys.weatherCities });
    }
  };
}

/** Adds a found city to the extra ones, for its weather: the home city and every clock stay. */
export function useAddCity() {
  const client = useQueryClient();
  const changed = useCitiesChanged();
  return useMutation({
    mutationKey: CITY_CHANGE,
    scope: CITIES_SCOPE,
    mutationFn: (city: City) =>
      api<WeatherCity>("/me/cities", {
        method: "POST",
        body: {
          name: city.name,
          admin: city.admin ?? null,
          country: city.country ?? null,
          lat: city.lat,
          lon: city.lon,
          timezone: city.timezone,
          geo_id: city.geo_id ?? null,
        },
      }),
    onSuccess: async (added) => {
      haptic("success");
      await client.cancelQueries({ queryKey: keys.weatherCities });
      client.setQueryData<WeatherCity[]>(keys.weatherCities, (list) =>
        list && !list.some((city) => city.id === added.id) ? [...list, added] : list);
    },
    onSettled: changed,
  });
}

/**
 * Deletes an extra city without asking (it is easy to add again): it leaves the list at once and
 * comes back if the server refuses — not on 404, when it is gone anyway.
 */
export function useDeleteCity() {
  const client = useQueryClient();
  const changed = useCitiesChanged();
  return useMutation({
    mutationKey: CITY_CHANGE,
    scope: CITIES_SCOPE,
    mutationFn: (id: number) => api<void>(`/me/cities/${id}`, { method: "DELETE" }),
    onMutate: async (id: number) => {
      await client.cancelQueries({ queryKey: keys.weatherCities });
      const city = client.getQueryData<WeatherCity[]>(keys.weatherCities)?.find((item) => item.id === id);
      client.setQueryData<WeatherCity[]>(keys.weatherCities, (list) => list?.filter((item) => item.id !== id));
      return { city };
    },
    onError: (error, _id, context) => {
      const city = context?.city;
      if (!city || isGone(error)) return;
      client.setQueryData<WeatherCity[]>(keys.weatherCities, (list) =>
        list && !list.some((item) => item.id === city.id) ? [...list, city].sort((a, b) => a.id - b.id) : list);
    },
    onSuccess: (_data, id) => {
      haptic("success");
      client.removeQueries({ queryKey: keys.forecast(id) });
    },
    onSettled: changed,
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
