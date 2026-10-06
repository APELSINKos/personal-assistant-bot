import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { LangProvider, type Lang } from "../i18n";
import { checklist, forecast, habit, me, note, scheduleSource, today, tula } from "../test/fixtures";
import { installTelegram } from "../test/fakeTelegram";
import { mockApi } from "../test/mockApi";
import { ApiError } from "./client";
import type { Agenda, City, Habit, HabitDetail, Me, Note, ScheduleState, Today, WeatherCity } from "./types";
import {
  createQueryClient, errorCode, keys, useAddCity, useAddingItems, useAddItem, useClearDone, useCreateHabit, useCreateNote,
  useDeleteCity, useDeleteHabit, useDeleteItem, useDeleteNote, useDeleteReminder, useDisconnectSchedule,
  useForecast, useHabit, useHabits, useMarkDay, useNotes, usePinNote, useRefreshSchedule, useScheduleAlerts,
  useSetCity, useSetItem, useSetMark, useShareHabit, useUpdateHabit, useUpdateMe, useUpdateNote, useUploadSchedule,
  useWeatherCities,
} from "./queries";

// Every mutation goes through `api()`, which needs a session (`initData()` non-null) before it
// will even attempt a request — without this, requests fail with "no_init_data" before ever
// reaching the mocked fetch below.
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

/** The same, with the toasts on screen: what a refusal says. */
function withToasts(client: ReturnType<typeof createQueryClient>, lang: Lang = "ru") {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <LangProvider lang={lang}>
          {children}
          <Toasts />
        </LangProvider>
      </QueryClientProvider>
    );
  };
}

/**
 * A fetch stub whose responses are resolved by hand, in whatever order the test chooses — needed
 * to reproduce races between an optimistic update and the request it's waiting on.
 */
function controllableFetch() {
  const pending: { method: string; path: string; body: unknown; resolve: (response: Response) => void }[] = [];
  const fetchMock = vi.fn((input: string, init: RequestInit = {}) => {
    const url = new URL(input, "http://app.test");
    const method = init.method ?? "GET";
    const path = url.pathname.replace(/^\/api/, "");
    const body: unknown = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    return new Promise<Response>((resolve) => {
      pending.push({ method, path, body, resolve });
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  function resolveAt(index: number, status: number, body: unknown) {
    const entry = pending[index];
    if (!entry) throw new Error(`no pending fetch call at index ${index}`);
    entry.resolve(new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
    }));
  }
  return { pending, resolveAt };
}

/**
 * Where each of the client's mutations stands, oldest first: "pending", "success" or "error". A
 * mutation turns "error" only after its own onError and onSettled have run, so this is how a test
 * waits for a rollback to be done without looking at the cache it is about to check.
 */
function statuses(client: QueryClient) {
  return client.getMutationCache().getAll().map((mutation) => mutation.state.status);
}

describe("optimistic mutation rollback", () => {
  it("rolls back a failed delete and shows a translated error toast", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.notes, [note]);
    const { pending, resolveAt } = controllableFetch();

    function Harness() {
      const del = useDeleteNote();
      return <button onClick={() => del.mutate(note.id)}>delete</button>;
    }
    render(
      <QueryClientProvider client={client}>
        <LangProvider lang="ru">
          <Harness />
          <Toasts />
        </LangProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "delete" }));
    // Optimistic: the row is gone from the cache before the request even settles.
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]));
    expect(pending).toHaveLength(1);

    act(() => {
      resolveAt(0, 503, { status: 503, code: "upstream_unavailable", title: "Upstream unavailable" });
    });

    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([note]));
  });

  it("does not bring back a row that is already gone on the server", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.notes, [note]);
    const { pending, resolveAt } = controllableFetch();
    const { result } = renderHook(() => ({ del: useDeleteNote(), notes: useNotes() }), {
      wrapper: wrapperFor(client),
    });

    act(() => {
      result.current.del.mutate(note.id);
    });
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]));
    act(() => {
      resolveAt(0, 404, { status: 404, code: "not_found", title: "Not found" });
    });
    await waitFor(() => expect(pending).toHaveLength(2)); // the list is asked for again
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]); // not restored meanwhile
    act(() => {
      resolveAt(1, 200, []);
    });
    await waitFor(() => expect(result.current.notes.isFetching).toBe(false));
    expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]);
  });

  it("rolls back a failed mark and shows a translated error toast", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.habits, [habit]);
    const { pending, resolveAt } = controllableFetch();

    function Harness() {
      const mark = useSetMark();
      return (
        <button onClick={() => mark.mutate({ id: habit.id, day: "2026-09-28", done: true })}>mark</button>
      );
    }
    render(
      <QueryClientProvider client={client}>
        <LangProvider lang="ru">
          <Harness />
          <Toasts />
        </LangProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "mark" }));
    // Optimistic: the mark is applied to the cache before the request even settles.
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBe(true));
    expect(pending).toHaveLength(1);

    act(() => {
      resolveAt(0, 500, { status: 500, code: "upstream_unavailable", title: "Upstream unavailable" });
    });

    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
    await waitFor(() =>
      expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBeNull());
  });
});

describe("useSetMark race safety", () => {
  it("serialises two quick taps and keeps the cache at the last one", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.habits, [habit]);
    const { pending, resolveAt } = controllableFetch();

    const { result } = renderHook(() => ({ mark: useSetMark(), habits: useHabits() }), {
      wrapper: wrapperFor(client),
    });

    // First tap: ⬜ -> ✅
    act(() => {
      result.current.mark.mutate({ id: habit.id, day: "2026-09-28", done: true });
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBe(true));
    expect(pending).toHaveLength(1);
    expect(pending[0]).toMatchObject({ method: "PUT", body: { done: true } });

    // Second tap, before the first settles: ✅ -> ❌
    act(() => {
      result.current.mark.mutate({ id: habit.id, day: "2026-09-28", done: false });
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBe(false));
    // The second PUT must not be sent yet — it's serialised behind the first via `scope`.
    expect(pending).toHaveLength(1);

    // First PUT settles. Its onSettled must NOT refetch while the second is still in flight —
    // otherwise a server response reflecting only the first tap would overwrite the cache with ✅.
    act(() => {
      resolveAt(0, 200, { ...habit, done_today: true });
    });
    await waitFor(() => expect(pending).toHaveLength(2)); // the second PUT is now released
    expect(pending[1]).toMatchObject({ method: "PUT", body: { done: false } });
    expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBe(false);

    // Second PUT settles: now it's the only mark mutation in flight, so this one may refresh.
    act(() => {
      resolveAt(1, 200, { ...habit, done_today: false });
    });
    await waitFor(() => expect(pending).toHaveLength(3)); // habits refetch triggered by useHabits()
    act(() => {
      resolveAt(2, 200, [{ ...habit, done_today: false }]);
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)?.[0]?.done_today).toBe(false));
  });
});

describe("useOptimisticRemove race safety", () => {
  // On habits: a note has a delete of its own, under the key every change of the notes shares.
  it("doesn't resurrect a row deleted just before another one settles", async () => {
    const client = createQueryClient();
    const habitA = habit;
    const habitB: Habit = { ...habit, id: 8, name: "Чтение" };
    client.setQueryData(keys.habits, [habitA, habitB]);
    const { pending, resolveAt } = controllableFetch();

    const { result } = renderHook(() => ({ del: useDeleteHabit(), habits: useHabits() }), {
      wrapper: wrapperFor(client),
    });

    act(() => {
      result.current.del.mutate(habitA.id);
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)).toEqual([habitB]));

    act(() => {
      result.current.del.mutate(habitB.id);
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)).toEqual([]));
    expect(pending).toHaveLength(2); // both DELETEs are independent, no shared scope needed

    // The first delete settles while the second is still in flight — must not refetch yet,
    // or a list that hasn't caught up with the second delete would resurrect habit B.
    act(() => {
      resolveAt(0, 204, null);
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(pending).toHaveLength(2); // no premature refetch
    expect(client.getQueryData<Habit[]>(keys.habits)).toEqual([]);

    act(() => {
      resolveAt(1, 204, null);
    });
    await waitFor(() => expect(pending).toHaveLength(3)); // now the list refetch is allowed
    act(() => {
      resolveAt(2, 200, []);
    });
    await waitFor(() => expect(client.getQueryData<Habit[]>(keys.habits)).toEqual([]));
  });
});

describe("useSetCity", () => {
  it("invalidates habits too, since their done_today depends on the city's date", async () => {
    const client = createQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    mockApi({
      "PUT /me/city": {
        id: 1, first_name: "Alex", language: "ru", language_setting: "auto",
        city: { name: "Париж", lat: 48.85, lon: 2.35, timezone: "Europe/Paris" },
        morning: { enabled: true, time: "08:00" },
      },
    });

    const { result } = renderHook(() => useSetCity(), { wrapper: wrapperFor(client) });
    act(() => {
      result.current.mutate({ name: "Париж", lat: 48.85, lon: 2.35, timezone: "Europe/Paris" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const invalidatedKeys = invalidateSpy.mock.calls.map((call) => call[0]?.queryKey);
    expect(invalidatedKeys).toContainEqual(keys.habits);
    expect(invalidatedKeys).toContainEqual(keys.today);
    expect(invalidatedKeys).toContainEqual(keys.reminders);
    expect(invalidatedKeys).toContainEqual(["agenda"]);
    expect(invalidatedKeys).toContainEqual(keys.money);  // the month's days follow the city's date
  });

  it("sends the found place's GeoNames id and refreshes the weather and its cities", async () => {
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const home = { name: "Тула", lat: 54.19, lon: 37.62, timezone: "Europe/Moscow" };
    const { calls } = mockApi({ "PUT /me/city": { ...me, city: home } });
    const { result } = renderHook(() => useSetCity(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(tula));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // The new home leaves the extra cities by its id: Тула is one of them.
    expect(calls[0]?.body).toEqual({ name: "Тула", lat: 54.19, lon: 37.62, timezone: "Europe/Moscow", geo_id: 480562 });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["weather"] }); // every forecast and the cities
  });
});

describe("useUpdateMe", () => {
  it("sends quick changes one at a time and keeps them all on screen meanwhile", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.me, me);
    const { pending, resolveAt } = controllableFetch();
    const { result } = renderHook(() => useUpdateMe(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ morning_enabled: false });
      result.current.mutate({ language: "en" });
    });
    await waitFor(() => expect(client.getQueryData<Me>(keys.me)?.language_setting).toBe("en"));
    expect(client.getQueryData<Me>(keys.me)?.morning.enabled).toBe(false);
    expect(pending).toHaveLength(1); // the second PATCH waits for the first
    expect(pending[0]).toMatchObject({ method: "PATCH", body: { morning_enabled: false } });

    // The first answer knows nothing of the language yet: it must not undo it on screen.
    act(() => {
      resolveAt(0, 200, { ...me, morning: { ...me.morning, enabled: false } });
    });
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "PATCH", body: { language: "en" } });
    expect(client.getQueryData<Me>(keys.me)?.language_setting).toBe("en");

    const last: Me = { ...me, language: "en", language_setting: "en", morning: { ...me.morning, enabled: false } };
    act(() => {
      resolveAt(1, 200, last);
    });
    await waitFor(() => expect(client.getQueryData<Me>(keys.me)).toEqual(last));
  });
});

describe("useDeleteReminder", () => {
  it("removes the item from every cached week at once", async () => {
    installTelegram();
    const week = (id: number) => ({ days: [{ date: "2026-09-29", items: [{ kind: "reminder", id, time: "09:00", text: "x", repeat: "none", description: null }] }] });
    mockApi({ "DELETE /reminders/5": () => ({ status: 204 }), "GET /agenda?from=2026-09-28&to=2026-10-04": { days: [] } });
    const client = createQueryClient();
    client.setQueryData(keys.agenda("2026-09-28", "2026-10-04"), week(5));
    const { result } = renderHook(() => useDeleteReminder(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(5));
    await waitFor(() =>
      expect(client.getQueryData<Agenda>(keys.agenda("2026-09-28", "2026-10-04"))?.days[0]?.items ?? []).toEqual([]),
    );
  });

  it("keeps the day's lessons", async () => {
    installTelegram();
    const lesson = { kind: "lesson", time: "09:00", end: "10:30", title: "x", lesson_kind: null, room: null };
    const reminder = { kind: "reminder", id: 5, time: "12:00", text: "x", repeat: "none", description: null };
    mockApi({ "DELETE /reminders/5": () => ({ status: 204 }), "GET /agenda?from=2026-09-28&to=2026-10-04": { days: [] } });
    const client = createQueryClient();
    client.setQueryData(keys.agenda("2026-09-28", "2026-10-04"), {
      days: [{ date: "2026-09-29", label: null, items: [lesson, reminder] }],
    });
    const { result } = renderHook(() => useDeleteReminder(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(5));
    await waitFor(() =>
      expect(client.getQueryData<Agenda>(keys.agenda("2026-09-28", "2026-10-04"))?.days[0]?.items).toEqual([lesson]),
    );
  });
});

describe("schedule", () => {
  it("uploads the picked file as the body and refreshes the calendar", async () => {
    const { calls } = mockApi({ "POST /schedule/file": { source: { ...scheduleSource, kind: "file" } } });
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUploadSchedule(), { wrapper: wrapperFor(client) });
    const file = new File(["BEGIN:VCALENDAR"], "Английский.ics", { type: "text/calendar" });
    act(() => result.current.mutate(file));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]?.path).toBe(`/schedule/file?name=${encodeURIComponent("Английский.ics")}`);
    expect(calls[0]?.body).toBe(file);
    expect(client.getQueryData<ScheduleState>(keys.schedule)?.source?.kind).toBe("file");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["agenda"] });
  });

  it("forgets the source on disconnect", async () => {
    mockApi({ "DELETE /schedule": { status: 204 } });
    const client = createQueryClient();
    client.setQueryData(keys.schedule, { source: scheduleSource });
    const { result } = renderHook(() => useDisconnectSchedule(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate());
    await waitFor(() => expect(client.getQueryData<ScheduleState>(keys.schedule)).toEqual({ source: null }));
  });

  it("gives connection failures their own texts", () => {
    for (const reason of ["forbidden_host", "unreachable", "too_large", "not_calendar", "source"]) {
      expect(errorCode(new ApiError(422, "validation_error", "Invalid input", { reason }))).toBe(reason);
    }
  });

  it("refreshes and forgets the source on 404 (disconnected from bot)", async () => {
    mockApi({ "POST /schedule/refresh": { status: 404, body: { status: 404, code: "not_found", title: "Not found" } } });
    const client = createQueryClient();
    client.setQueryData(keys.schedule, { source: scheduleSource });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useRefreshSchedule(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate());
    await waitFor(() => expect(client.getQueryData<ScheduleState>(keys.schedule)).toEqual({ source: null }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["agenda"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.today });
  });

  it("alerts and forgets the source on 404 (disconnected from bot)", async () => {
    mockApi({ "PATCH /schedule": { status: 404, body: { status: 404, code: "not_found", title: "Not found" } } });
    const client = createQueryClient();
    client.setQueryData(keys.schedule, { source: scheduleSource });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useScheduleAlerts(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(15));
    await waitFor(() => expect(client.getQueryData<ScheduleState>(keys.schedule)).toEqual({ source: null }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["agenda"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.today });
  });

  it("disconnects and forgets the source on 404 (disconnected from bot)", async () => {
    mockApi({ "DELETE /schedule": { status: 404, body: { status: 404, code: "not_found", title: "Not found" } } });
    const client = createQueryClient();
    client.setQueryData(keys.schedule, { source: scheduleSource });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useDisconnectSchedule(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate());
    await waitFor(() => expect(client.getQueryData<ScheduleState>(keys.schedule)).toEqual({ source: null }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["agenda"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.today });
  });

  it("keeps the source when an upload is answered 404 (that cannot mean it was disconnected)", async () => {
    mockApi({ "POST /schedule/file": { status: 404, body: { status: 404, code: "not_found", title: "Not found" } } });
    const client = createQueryClient();
    client.setQueryData(keys.schedule, { source: scheduleSource });
    const { result } = renderHook(() => useUploadSchedule(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(new File(["BEGIN:VCALENDAR"], "x.ics")));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData<ScheduleState>(keys.schedule)).toEqual({ source: scheduleSource });
  });

  it("upload also invalidates today", async () => {
    mockApi({ "POST /schedule/file": { source: { ...scheduleSource, kind: "file" } } });
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUploadSchedule(), { wrapper: wrapperFor(client) });
    const file = new File(["BEGIN:VCALENDAR"], "Английский.ics", { type: "text/calendar" });
    act(() => result.current.mutate(file));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.today });
  });
});

const DETAIL: HabitDetail = {
  ...habit,
  year_from: "2025-09-29",
  // the last week, from Monday 28 September: done, no mark, then Wednesday to Sunday ahead
  year: "1".repeat(364) + "1-" + ".".repeat(5),
};

describe("habits", () => {
  it("fetches one habit with its year", async () => {
    const { calls } = mockApi({ "GET /habits/7": DETAIL });
    const { result } = renderHook(() => useHabit(7), { wrapper: wrapperFor(createQueryClient()) });
    await waitFor(() => expect(result.current.data?.year).toBe(DETAIL.year));
    expect(calls[0]?.path).toBe("/habits/7");
  });

  it("creates a habit with its look and goal", async () => {
    const { calls } = mockApi({ "POST /habits": { status: 201, body: habit } });
    const { result } = renderHook(() => useCreateHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate({ name: "Бег", emoji: "🏃", color: "sky", weekly_goal: 3 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]?.body).toEqual({ name: "Бег", emoji: "🏃", color: "sky", weekly_goal: 3 });
  });

  it("changes a habit and refreshes the list, the open habit and today", async () => {
    const { calls } = mockApi({ "PATCH /habits/7": habit });
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useUpdateHabit(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ id: 7, patch: { weekly_goal: 3 } }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "PATCH", path: "/habits/7", body: { weekly_goal: 3 } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["habits"] }); // the list and every open habit
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["today"] });
  });

  it("shows a day's new mark at once and takes it back if the server refuses", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.habit(7), DETAIL);
    const { result } = renderHook(() => useMarkDay(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ id: 7, day: "2026-09-29", done: true }));
    await waitFor(() => expect(client.getQueryData<HabitDetail>(keys.habit(7))?.year.slice(364, 366)).toBe("11"));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "PUT", path: "/habits/7/marks/2026-09-29", body: { done: true } });
    act(() => resolveAt(0, 500, { status: 500, code: "internal_error" }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData<HabitDetail>(keys.habit(7))?.year).toBe(DETAIL.year);
  });
});

// Marks share one serial scope: onMutate runs for every tap at once, while the requests go one by one.
// So when a request is refused, the taps made after it are already on screen and must stay there.
describe("a refused mark with later taps queued behind it", () => {
  const refused = { status: 422, code: "validation_error", title: "Invalid input" };
  const MONDAY = "2026-09-28";
  const TUESDAY = "2026-09-29";

  describe("in an open habit", () => {
    // DETAIL's last week; the tests read the two characters for Monday and Tuesday.
    // "-" is no mark, "1" done, "0" missed.
    const yearOf = (monday: string, tuesday: string) =>
      "1".repeat(364) + monday + tuesday + ".".repeat(5);
    const days = (client: QueryClient) =>
      client.getQueryData<HabitDetail>(keys.habit(7))?.year.slice(364, 366);

    function open(monday = "-", tuesday = "-") {
      const server = controllableFetch();
      const client = createQueryClient();
      client.setQueryData(keys.habit(7), { ...DETAIL, year: yearOf(monday, tuesday) });
      const { result } = renderHook(() => useMarkDay(), { wrapper: wrapperFor(client) });
      const tap = (day: string, done: boolean | null) =>
        act(() => result.current.mutate({ id: 7, day, done }));
      return { ...server, client, tap };
    }

    it("takes back only the refused day, and a later tap on another day stays", async () => {
      const { client, pending, resolveAt, tap } = open();
      tap(MONDAY, true);
      await waitFor(() => expect(days(client)).toBe("1-"));
      tap(TUESDAY, true);
      await waitFor(() => expect(days(client)).toBe("11"));

      act(() => resolveAt(0, 422, refused)); // Monday's request is refused
      await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
      expect(days(client)).toBe("-1"); // Monday is unmarked again, Tuesday still shows its tap

      await waitFor(() => expect(pending).toHaveLength(2));
      act(() => resolveAt(1, 200, habit)); // Tuesday's is accepted
      await waitFor(() => expect(statuses(client)).toEqual(["error", "success"]));
      expect(days(client)).toBe("-1");
    });

    it("brings no refused mark back when the later tap is refused too", async () => {
      const { client, pending, resolveAt, tap } = open();
      tap(MONDAY, true);
      await waitFor(() => expect(days(client)).toBe("1-"));
      tap(TUESDAY, true);
      await waitFor(() => expect(days(client)).toBe("11"));

      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(pending).toHaveLength(2)); // Tuesday's request goes out next
      act(() => resolveAt(1, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "error"]));
      expect(days(client)).toBe("--");
    });

    it.each([
      { name: "done", was: "1", next: false, onScreen: "0" },
      { name: "missed", was: "0", next: true, onScreen: "1" },
    ])("puts back a $name day when its tap is refused", async ({ was, next, onScreen }) => {
      const { client, resolveAt, tap } = open(was);
      tap(MONDAY, next);
      await waitFor(() => expect(days(client)).toBe(onScreen + "-"));
      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error"]));
      expect(days(client)).toBe(was + "-");
    });

    it("leaves a day to the later tap on it when the earlier one is refused", async () => {
      const { client, pending, resolveAt, tap } = open();
      tap(MONDAY, true);
      await waitFor(() => expect(days(client)).toBe("1-"));
      tap(MONDAY, false);
      await waitFor(() => expect(days(client)).toBe("0-"));

      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
      expect(days(client)).toBe("0-"); // the second tap owns the day now: it is not undone with the first

      await waitFor(() => expect(pending).toHaveLength(2));
      act(() => resolveAt(1, 200, habit));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "success"]));
      expect(days(client)).toBe("0-");
    });

    it("still sends a mark for a habit that is not cached, and caches nothing", async () => {
      const { pending, resolveAt } = controllableFetch();
      const client = createQueryClient();
      const { result } = renderHook(() => useMarkDay(), { wrapper: wrapperFor(client) });
      act(() => result.current.mutate({ id: 7, day: MONDAY, done: true }));
      await waitFor(() => expect(pending).toHaveLength(1));
      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error"]));
      expect(client.getQueryData(keys.habit(7))).toBeUndefined();
    });
  });

  describe("on the habits list and Today", () => {
    const sport: Habit = { ...habit, done_today: false };
    const reading: Habit = { ...habit, id: 8, name: "Reading", done_today: null };
    // What each cache shows for the two habits, in order; undefined where a cache is not there.
    const shown = (client: QueryClient) => ({
      list: client.getQueryData<Habit[]>(keys.habits)?.map((item) => item.done_today),
      today: client.getQueryData<Today>(keys.today)?.habits.items.map((item) => item.done_today),
    });

    function cached(where: { list: boolean; today: boolean }) {
      const server = controllableFetch();
      const client = createQueryClient();
      if (where.list) client.setQueryData(keys.habits, [sport, reading]);
      if (where.today) {
        client.setQueryData(keys.today, { ...today, habits: { done: 0, total: 2, items: [sport, reading] } });
      }
      const { result } = renderHook(() => useSetMark(), { wrapper: wrapperFor(client) });
      const tap = (id: number, done: boolean | null) =>
        act(() => result.current.mutate({ id, day: today.date, done }));
      return { ...server, client, tap };
    }

    it("takes back only the refused habit's mark, in the list and in Today", async () => {
      const { client, pending, resolveAt, tap } = cached({ list: true, today: true });
      tap(7, true);
      await waitFor(() => expect(shown(client)).toEqual({ list: [true, null], today: [true, null] }));
      tap(8, true);
      await waitFor(() => expect(shown(client)).toEqual({ list: [true, true], today: [true, true] }));

      act(() => resolveAt(0, 422, refused)); // the first habit's request is refused
      await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
      // The first habit is back to its earlier mark, the second still shows its tap.
      expect(shown(client)).toEqual({ list: [false, true], today: [false, true] });

      await waitFor(() => expect(pending).toHaveLength(2));
      act(() => resolveAt(1, 200, { ...reading, done_today: true }));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "success"]));
      expect(shown(client)).toEqual({ list: [false, true], today: [false, true] });
    });

    it("reads the earlier mark from Today when the habits list was never opened", async () => {
      const { client, pending, resolveAt, tap } = cached({ list: false, today: true });
      tap(7, true);
      await waitFor(() => expect(shown(client).today).toEqual([true, null]));
      tap(8, true);
      await waitFor(() => expect(shown(client).today).toEqual([true, true]));

      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
      expect(shown(client)).toEqual({ list: undefined, today: [false, true] }); // and no list appeared

      await waitFor(() => expect(pending).toHaveLength(2));
      act(() => resolveAt(1, 200, { ...reading, done_today: true }));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "success"]));
      expect(shown(client)).toEqual({ list: undefined, today: [false, true] });
    });

    it("leaves a habit to the later tap on it when the earlier one is refused", async () => {
      const { client, pending, resolveAt, tap } = cached({ list: true, today: true });
      tap(8, true);
      await waitFor(() => expect(shown(client).list).toEqual([false, true]));
      tap(8, false);
      await waitFor(() => expect(shown(client).list).toEqual([false, false]));

      act(() => resolveAt(0, 422, refused));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
      // The second tap owns the habit now: it is not undone with the first.
      expect(shown(client)).toEqual({ list: [false, false], today: [false, false] });

      await waitFor(() => expect(pending).toHaveLength(2));
      act(() => resolveAt(1, 200, { ...reading, done_today: false }));
      await waitFor(() => expect(statuses(client)).toEqual(["error", "success"]));
      expect(shown(client)).toEqual({ list: [false, false], today: [false, false] });
    });
  });
});

describe("useShareHabit", () => {
  it("shares through a prepared message in Telegram 8.0", async () => {
    const telegram = installTelegram();
    const { calls } = mockApi({ "POST /habits/7/share": { prepared_id: "prepared-1" } });
    const { result } = renderHook(() => useShareHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(7));
    await waitFor(() => expect(result.current.data).toBe("shared"));
    expect(telegram.shareMessage).toHaveBeenCalledWith("prepared-1", expect.any(Function));
    expect(calls.map((call) => call.path)).toEqual(["/habits/7/share"]);
  });

  it("says when the user closed the chat picker", async () => {
    installTelegram({ shareMessage: vi.fn((_id: string, callback?: (sent: boolean) => void) => callback?.(false)) });
    mockApi({ "POST /habits/7/share": { prepared_id: "prepared-1" } });
    const { result } = renderHook(() => useShareHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(7));
    await waitFor(() => expect(result.current.data).toBe("cancelled"));
  });

  it("has the bot send the card on an older Telegram", async () => {
    const telegram = installTelegram({}, "7.10");
    const { calls } = mockApi({ "POST /habits/7/card": { status: 204 } });
    const { result } = renderHook(() => useShareHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(7));
    await waitFor(() => expect(result.current.data).toBe("sent"));
    expect(telegram.shareMessage).not.toHaveBeenCalled();
    expect(calls.map((call) => call.path)).toEqual(["/habits/7/card"]);
  });

  it("has the bot send the card when the server cannot prepare messages", async () => {
    const { calls } = mockApi({
      "POST /habits/7/share": { status: 503, body: { status: 503, code: "upstream_unavailable" } },
      "POST /habits/7/card": { status: 204 },
    });
    const { result } = renderHook(() => useShareHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(7));
    await waitFor(() => expect(result.current.data).toBe("sent"));
    expect(calls.map((call) => call.path)).toEqual(["/habits/7/share", "/habits/7/card"]);
  });

  it("does not fall back past a refusal meant for the user", async () => {
    const { calls } = mockApi({
      "POST /habits/7/share": { status: 429, body: { status: 429, code: "rate_limited" } },
    });
    const { result } = renderHook(() => useShareHabit(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(7));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls.map((call) => call.path)).toEqual(["/habits/7/share"]);
  });
});

describe("errorCode", () => {
  const limit = (details: Record<string, unknown>) => new ApiError(409, "limit_reached", "Limit reached", details);
  const refused = (field: string, reason: string) =>
    new ApiError(422, "validation_error", "Invalid input", { field, reason });

  it("gives a limit its own words where the dictionary has them", () => {
    expect(errorCode(limit({ entity: "pinned_note", limit: 5 }))).toBe("limit_pinned_note");
    expect(errorCode(limit({ entity: "note_item", limit: 20 }))).toBe("limit_note_item");
    expect(errorCode(limit({ entity: "city", limit: 4 }))).toBe("limit_city");
    // No words of its own, or no entity: the general text.
    expect(errorCode(limit({ entity: "note", limit: 50 }))).toBe("limit_reached");
    expect(errorCode(limit({ entity: "habit", limit: 20 }))).toBe("limit_reached");
    expect(errorCode(limit({}))).toBe("limit_reached");
  });

  it("tells a city that is on the list already from other repeats", () => {
    expect(errorCode(refused("city", "duplicate"))).toBe("duplicate_city");
    expect(errorCode(refused("name", "duplicate"))).toBe("duplicate");
    expect(errorCode(refused("city", "invalid"))).toBe("validation_error");
  });
});

describe("the weather", () => {
  it("asks for the home city without a parameter and for an extra city by its id", async () => {
    const extra = { ...forecast, city: { id: 3, name: "Тула", home: false } };
    const { calls } = mockApi({ "GET /weather": forecast, "GET /weather?city=3": extra });
    const client = createQueryClient();
    const home = renderHook(() => useForecast(0), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(home.result.current.data?.city.home).toBe(true));
    const other = renderHook(() => useForecast(3), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(other.result.current.data?.city.name).toBe("Тула"));
    expect(calls.map((call) => call.path)).toEqual(["/weather", "/weather?city=3"]);
  });

  it("does not ask again for a city that is gone", async () => {
    const { calls } = mockApi({}); // 404 to everything
    const { result } = renderHook(() => useForecast(9), { wrapper: wrapperFor(createQueryClient()) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 404 });
    expect(calls).toHaveLength(1);
  });

  it("lists the extra cities", async () => {
    const { calls } = mockApi({ "GET /me/cities": [tula] });
    const { result } = renderHook(() => useWeatherCities(), { wrapper: wrapperFor(createQueryClient()) });
    await waitFor(() => expect(result.current.data).toEqual([tula]));
    expect(calls[0]?.path).toBe("/me/cities");
  });
});

const KAZAN: City = {
  name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow",
  geo_id: 551487,
};
const KAZAN_KEPT: WeatherCity = {
  id: 4, name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow",
  geo_id: 551487,
};

describe("the extra cities", () => {
  const ids = (client: QueryClient) => client.getQueryData<WeatherCity[]>(keys.weatherCities)?.map((city) => city.id);

  it("adds a found city with all the server keeps of it", async () => {
    const { calls } = mockApi({ "POST /me/cities": { status: 201, body: KAZAN_KEPT } });
    const client = createQueryClient();
    client.setQueryData(keys.weatherCities, [tula]);
    const { result } = renderHook(() => useAddCity(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(KAZAN));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toEqual({
      method: "POST",
      path: "/me/cities",
      body: {
        name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow",
        geo_id: 551487,
      },
    });
    expect(ids(client)).toEqual([3, 4]);
  });

  it("sends what a found place lacks as null", async () => {
    const { calls } = mockApi({ "POST /me/cities": { status: 201, body: KAZAN_KEPT } });
    const { result } = renderHook(() => useAddCity(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate({ name: "Казань", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow" }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]?.body).toEqual({
      name: "Казань", admin: null, country: null, lat: 55.79, lon: 49.12, timezone: "Europe/Moscow", geo_id: null,
    });
  });

  it("takes a city off the list at once and puts it back if the server refuses", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.weatherCities, [tula, KAZAN_KEPT]);
    const { result } = renderHook(() => useDeleteCity(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(3));
    await waitFor(() => expect(ids(client)).toEqual([4]));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "DELETE", path: "/me/cities/3" });
    act(() => resolveAt(0, 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(ids(client)).toEqual([3, 4]); // back in its place
  });

  it("does not bring back a city that is gone already", async () => {
    mockApi({ "DELETE /me/cities/3": { status: 404, body: { status: 404, code: "not_found" } } });
    const client = createQueryClient();
    client.setQueryData(keys.weatherCities, [tula]);
    const { result } = renderHook(() => useDeleteCity(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate(3));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(ids(client)).toEqual([]);
  });

  it("sends additions and deletions one at a time and asks for the list after the last", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.weatherCities, [tula]);
    client.setQueryData(keys.forecast(3), { ...forecast, city: { id: 3, name: "Тула", home: false } });
    const { result } = renderHook(
      () => ({ add: useAddCity(), remove: useDeleteCity(), list: useWeatherCities() }),
      { wrapper: wrapperFor(client) },
    );
    act(() => {
      result.current.add.mutate(KAZAN);
      result.current.remove.mutate(3);
    });
    await waitFor(() => expect(ids(client)).toEqual([])); // the deletion shows at once
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "POST", path: "/me/cities" }); // the deletion waits for it

    act(() => resolveAt(0, 201, KAZAN_KEPT));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "DELETE", path: "/me/cities/3" });
    expect(ids(client)).toEqual([4]); // no list fetched in between to bring Тула back

    act(() => resolveAt(1, 204, null));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(pending[2]).toMatchObject({ method: "GET", path: "/me/cities" });
    expect(client.getQueryData(keys.forecast(3))).toBeUndefined(); // the deleted city's forecast is dropped
  });

  it("words a refused city as the server means it", async () => {
    mockApi({
      "POST /me/cities": ({ body }: { body: unknown }) =>
        (body as City).name === "Казань"
          ? { status: 409, body: { status: 409, code: "limit_reached", entity: "city", limit: 4 } }
          : { status: 422, body: { status: 422, code: "validation_error", field: "city", reason: "duplicate" } },
    });
    const { result } = renderHook(() => useAddCity(), { wrapper: withToasts(createQueryClient()) });
    act(() => result.current.mutate(KAZAN));
    expect(await screen.findByText("Уже 5 городов вместе с домашним — удали лишний")).toBeInTheDocument();
    act(() => result.current.mutate({ ...KAZAN, name: "Тула" }));
    expect(await screen.findByText("Этот город уже в списке")).toBeInTheDocument();
  });
});

describe("notes with pins and items", () => {
  it("creates a checklist with its items, pinned at once, and shows it on top", async () => {
    const { calls } = mockApi({ "POST /notes": { status: 201, body: checklist } });
    const client = createQueryClient();
    client.setQueryData(keys.notes, [note]);
    const { result } = renderHook(() => useCreateNote(), { wrapper: wrapperFor(client) });
    act(() => result.current.mutate({ text: "Покупки", items: ["молоко", "хлеб"], pinned: true }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toEqual({
      method: "POST", path: "/notes", body: { text: "Покупки", items: ["молоко", "хлеб"], pinned: true },
    });
    expect(client.getQueryData<Note[]>(keys.notes)?.map((shown) => shown.id)).toEqual([12, 11]);
  });

  it("takes back only the text of a refused save: an item checked meanwhile stays checked", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.notes, [checklist]);
    const { result } = renderHook(
      () => ({ save: useUpdateNote(), check: useSetItem(), notes: useNotes() }),
      { wrapper: wrapperFor(client) },
    );
    const shown = () => client.getQueryData<Note[]>(keys.notes)?.[0];
    act(() => result.current.save.mutate({ id: 12, text: "Покупки на неделю" }));
    act(() => result.current.check.mutate({ note: 12, id: 31, done: true }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(shown()?.text).toBe("Покупки на неделю");
    expect(shown()?.items[0]?.done).toBe(true);
    const save = pending.findIndex((request) => request.path === "/notes/12");
    const check = pending.findIndex((request) => request.path === "/notes/12/items/31");
    expect(pending[save]).toMatchObject({ method: "PATCH", body: { text: "Покупки на неделю" } });

    act(() => resolveAt(save, 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(result.current.save.isError).toBe(true));
    expect(shown()?.text).toBe("Покупки");
    expect(shown()?.items[0]?.done).toBe(true);
    expect(pending).toHaveLength(2); // no list while the check is on its way

    act(() => resolveAt(check, 200, { id: 31, text: "молоко", done: true }));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });

  it("pins at once and puts the pin back, in the words of §12, at five pinned notes", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.notes, [note]);
    const { result } = renderHook(() => usePinNote(), { wrapper: withToasts(client) });
    const pinned = () => client.getQueryData<Note[]>(keys.notes)?.[0]?.pinned;
    act(() => result.current.mutate({ id: 11, pinned: true }));
    await waitFor(() => expect(pinned()).toBe(true));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "PATCH", path: "/notes/11", body: { pinned: true } });
    act(() => resolveAt(0, 409, { status: 409, code: "limit_reached", entity: "pinned_note", limit: 5 }));
    expect(await screen.findByText("Закрепить можно не больше 5 заметок — открепи одну")).toBeInTheDocument();
    expect(pinned()).toBe(false);
  });

  it("sends quick taps on the pin one at a time and leaves the pin to the later tap", async () => {
    const { pending, resolveAt } = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.notes, [note]);
    const { result } = renderHook(() => ({ pin: usePinNote(), notes: useNotes() }), { wrapper: wrapperFor(client) });
    const pinned = () => client.getQueryData<Note[]>(keys.notes)?.[0]?.pinned;
    act(() => result.current.pin.mutate({ id: 11, pinned: true }));
    act(() => result.current.pin.mutate({ id: 11, pinned: false }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pinned()).toBe(false);

    act(() => resolveAt(0, 409, { status: 409, code: "limit_reached", entity: "pinned_note", limit: 5 }));
    await waitFor(() => expect(pending).toHaveLength(2)); // the second tap goes now
    expect(pending[1]).toMatchObject({ method: "PATCH", body: { pinned: false } });
    expect(pinned()).toBe(false); // not undone with the first

    act(() => resolveAt(1, 200, note));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });
});

describe("the items of a checklist", () => {
  // Покупки (12): молоко to buy (31), хлеб bought (32); pinned, so «Сегодня» counts 1 of 2.
  function open(wrapper: (client: QueryClient) => ({ children }: { children: ReactNode }) => ReactNode = wrapperFor) {
    const server = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.notes, [checklist]);
    client.setQueryData<Today>(keys.today, {
      ...today, pinned_notes: [{ id: 12, text: "Покупки", done: 1, total: 2 }],
    });
    const { result } = renderHook(
      () => ({
        add: useAddItem(), set: useSetItem(), remove: useDeleteItem(), clear: useClearDone(), notes: useNotes(),
      }),
      { wrapper: wrapper(client) },
    );
    return { ...server, client, result };
  }

  /** The checklist as the screen shows it, and how «Сегодня» counts it. */
  function shown(client: QueryClient) {
    const pinned = client.getQueryData<Today>(keys.today)?.pinned_notes[0];
    return {
      items: client.getQueryData<Note[]>(keys.notes)?.[0]?.items.map((item) => `${item.done ? "✅" : "⬜"} ${item.text}`),
      today: pinned && `${pinned.done}/${pinned.total}`,
    };
  }

  it("checks at once, on «Сегодня» too, one request at a time, and asks for the notes after the last", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    await waitFor(() => expect(shown(client)).toEqual({ items: ["✅ молоко", "✅ хлеб"], today: "2/2" }));
    act(() => result.current.set.mutate({ note: 12, id: 32, done: false }));
    await waitFor(() => expect(shown(client)).toEqual({ items: ["✅ молоко", "⬜ хлеб"], today: "1/2" }));
    await waitFor(() => expect(pending).toHaveLength(1)); // the second waits for the first
    expect(pending[0]).toMatchObject({ method: "PATCH", path: "/notes/12/items/31", body: { done: true } });

    act(() => resolveAt(0, 200, { id: 31, text: "молоко", done: true }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "PATCH", path: "/notes/12/items/32", body: { done: false } });

    act(() => resolveAt(1, 200, { id: 32, text: "хлеб", done: false }));
    await waitFor(() => expect(pending).toHaveLength(3)); // only now
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });

  it("takes back only the refused item", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.set.mutate({ note: 12, id: 32, done: false }));
    await waitFor(() => expect(shown(client).items).toEqual(["✅ молоко", "⬜ хлеб"]));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 422, { status: 422, code: "validation_error" }));
    await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
    expect(shown(client)).toEqual({ items: ["⬜ молоко", "⬜ хлеб"], today: "0/2" });
  });

  it("leaves an item to the later tap on it when the earlier one is refused", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.set.mutate({ note: 12, id: 31, done: false }));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 422, { status: 422, code: "validation_error" }));
    await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
    expect(shown(client).items).toEqual(["⬜ молоко", "✅ хлеб"]);
  });

  it("shows a new item once the server has given it an id, and only then sends what came after", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.add.mutate({ note: 12, text: "сыр" }));
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "POST", path: "/notes/12/items", body: { text: "сыр" } });
    expect(shown(client).items).toEqual(["✅ молоко", "✅ хлеб"]); // no item without an id

    act(() => resolveAt(0, 201, { id: 33, text: "сыр", done: false }));
    await waitFor(() => expect(shown(client)).toEqual({ items: ["✅ молоко", "✅ хлеб", "⬜ сыр"], today: "2/3" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "PATCH", path: "/notes/12/items/31" });
  });

  it("deletes an item at once and puts it back in its place if the server refuses", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.remove.mutate({ note: 12, id: 31 }));
    await waitFor(() => expect(shown(client)).toEqual({ items: ["✅ хлеб"], today: "1/1" }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "DELETE", path: "/notes/12/items/31" });
    act(() => resolveAt(0, 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(pending).toHaveLength(2)); // the notes, once it is back
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(shown(client)).toEqual({ items: ["⬜ молоко", "✅ хлеб"], today: "1/2" });
  });

  it("says nothing when the item to delete is gone already, and asks for the notes", async () => {
    const { client, pending, resolveAt, result } = open(withToasts);
    act(() => result.current.remove.mutate({ note: 12, id: 31 }));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 404, { status: 404, code: "not_found" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(shown(client).items).toEqual(["✅ хлеб"]);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("says once that a checked item's note is gone, takes nothing back and asks for the notes", async () => {
    // In English the two texts differ: the item's own «This is already gone», never the general one too.
    const { client, pending, resolveAt, result } = open((client) => withToasts(client, "en"));
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 404, { status: 404, code: "not_found" }));
    expect(await screen.findByText("This is already gone")).toBeInTheDocument();
    expect(screen.queryByText("That is already gone")).not.toBeInTheDocument();
    expect(shown(client).items).toEqual(["✅ молоко", "✅ хлеб"]);
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
  });

  it("says once that the note to add an item to is gone, adds nothing and asks for the notes", async () => {
    const { client, pending, resolveAt, result } = open((client) => withToasts(client, "en"));
    act(() => result.current.add.mutate({ note: 12, text: "сыр" }));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 404, { status: 404, code: "not_found" }));
    expect(await screen.findByText("This is already gone")).toBeInTheDocument();
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(screen.getAllByText("This is already gone")).toHaveLength(1);
    expect(screen.queryByText("That is already gone")).not.toBeInTheDocument();
    expect(shown(client)).toEqual({ items: ["⬜ молоко", "✅ хлеб"], today: "1/2" });
  });

  it("removes the checked items at once and puts them back if the server refuses", async () => {
    const { client, pending, resolveAt, result } = open();
    act(() => result.current.clear.mutate(12));
    await waitFor(() => expect(shown(client)).toEqual({ items: ["⬜ молоко"], today: "0/1" }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(pending[0]).toMatchObject({ method: "DELETE", path: "/notes/12/items" });
    act(() => resolveAt(0, 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(pending).toHaveLength(2)); // the notes, once they are back
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(shown(client)).toEqual({ items: ["⬜ молоко", "✅ хлеб"], today: "1/2" });
  });

  it("says once that the note to clear is gone, puts nothing back and asks for the notes", async () => {
    const { client, pending, resolveAt, result } = open((client) => withToasts(client, "en"));
    act(() => result.current.clear.mutate(12));
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => resolveAt(0, 404, { status: 404, code: "not_found" }));
    expect(await screen.findByText("This is already gone")).toBeInTheDocument();
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1]).toMatchObject({ method: "GET", path: "/notes" });
    expect(screen.getAllByText("This is already gone")).toHaveLength(1);
    expect(screen.queryByText("That is already gone")).not.toBeInTheDocument();
    expect(shown(client)).toEqual({ items: ["⬜ молоко"], today: "0/1" });
  });

  it("asks the server to remove the checked items only", async () => {
    const { calls } = mockApi({ "DELETE /notes/12/items?done=true": { status: 204 } });
    const { result } = renderHook(() => useClearDone(), { wrapper: wrapperFor(createQueryClient()) });
    act(() => result.current.mutate(12));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/notes/12/items?done=true" });
  });

  it("counts the items still on their way to a note, queued ones too, and no other note's", async () => {
    const { client, pending, resolveAt } = open();
    const { result } = renderHook(
      () => ({ add: useAddItem(), set: useSetItem(), adding: useAddingItems(12), other: useAddingItems(11) }),
      { wrapper: wrapperFor(client) },
    );
    act(() => result.current.add.mutate({ note: 12, text: "сыр" }));
    act(() => result.current.set.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.add.mutate({ note: 12, text: "масло" })); // queued behind the check
    act(() => result.current.add.mutate({ note: 11, text: "батон" }));
    await waitFor(() => expect(result.current.adding).toBe(2));
    expect(result.current.other).toBe(1);
    await waitFor(() => expect(pending).toHaveLength(1));

    act(() => resolveAt(0, 201, { id: 33, text: "сыр", done: false }));
    // Shown in the note now, and no longer counted on its way: never twice, never missing.
    await waitFor(() => expect(result.current.adding).toBe(1));
    expect(client.getQueryData<Note[]>(keys.notes)?.[0]?.items.map((item) => item.id)).toEqual([31, 32, 33]);
  });
});

describe("notes deleted and created while other changes are on their way", () => {
  // Покупки (12) pinned on top, then Купить хлеб (11) and Позвонить маме (10).
  const call: Note = { ...note, id: 10, text: "Позвонить маме" };
  const checked = { id: 31, text: "молоко", done: true };

  function open() {
    const server = controllableFetch();
    const client = createQueryClient();
    client.setQueryData(keys.notes, [checklist, note, call]);
    const { result } = renderHook(
      () => ({
        create: useCreateNote(), remove: useDeleteNote(), pin: usePinNote(), check: useSetItem(), notes: useNotes(),
      }),
      { wrapper: withToasts(client) },
    );
    /** Where a request stands among those sent so far. */
    const sent = (method: string, path: string) =>
      server.pending.findIndex((request) => request.method === method && request.path === path);
    return { ...server, client, result, sent };
  }

  const ids = (client: QueryClient) => client.getQueryData<Note[]>(keys.notes)?.map((shown) => shown.id);

  it("asks for no notes while a note is being deleted: a check that ends first does not bring it back", async () => {
    const { client, pending, resolveAt, result, sent } = open();
    act(() => result.current.remove.mutate(11));
    act(() => result.current.check.mutate({ note: 12, id: 31, done: true }));
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => resolveAt(sent("PATCH", "/notes/12/items/31"), 200, checked));
    await waitFor(() => expect(statuses(client)).toEqual(["pending", "success"]));
    expect(pending).toHaveLength(2);
    expect(ids(client)).toEqual([12, 10]);

    act(() => resolveAt(sent("DELETE", "/notes/11"), 204, null));
    await waitFor(() => expect(pending).toHaveLength(3)); // only now
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });

  it("asks for no notes while a check is on its way: a delete that ends first does not undo the check", async () => {
    const { client, pending, resolveAt, result, sent } = open();
    act(() => result.current.check.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.remove.mutate(11));
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => resolveAt(sent("DELETE", "/notes/11"), 204, null));
    await waitFor(() => expect(statuses(client)).toEqual(["pending", "success"]));
    expect(pending).toHaveLength(2);
    expect(client.getQueryData<Note[]>(keys.notes)?.[0]?.items[0]?.done).toBe(true);

    act(() => resolveAt(sent("PATCH", "/notes/12/items/31"), 200, checked));
    await waitFor(() => expect(pending).toHaveLength(3)); // only now
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });

  it("puts back only the note of a refused delete, in its place: a check and a pin made meanwhile stay", async () => {
    const { client, pending, resolveAt, result, sent } = open();
    act(() => result.current.remove.mutate(11));
    act(() => result.current.check.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.pin.mutate({ id: 10, pinned: true }));
    await waitFor(() => expect(pending).toHaveLength(3));
    act(() => resolveAt(sent("DELETE", "/notes/11"), 503, { status: 503, code: "upstream_unavailable" }));
    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
    await waitFor(() => expect(statuses(client)).toEqual(["error", "pending", "pending"]));
    const notes = client.getQueryData<Note[]>(keys.notes);
    expect(notes?.map((shown) => shown.id)).toEqual([12, 11, 10]);
    expect(notes?.[0]?.items[0]?.done).toBe(true);
    expect(notes?.[2]?.pinned).toBe(true);
    expect(pending).toHaveLength(3); // the notes wait for the check and the pin
  });

  it("leaves away a note still being deleted when another delete is refused", async () => {
    const { client, pending, resolveAt, result, sent } = open();
    act(() => result.current.remove.mutate(12));
    act(() => result.current.remove.mutate(11));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(ids(client)).toEqual([10]);
    act(() => resolveAt(sent("DELETE", "/notes/12"), 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(statuses(client)).toEqual(["error", "pending"]));
    expect(ids(client)).toEqual([12, 10]);
    expect(pending).toHaveLength(2); // no notes while the other delete is on its way

    act(() => resolveAt(sent("DELETE", "/notes/11"), 503, { status: 503, code: "upstream_unavailable" }));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
    expect(ids(client)).toEqual([12, 11, 10]);
  });

  it("shows a created note at once while a check is on its way, and asks for the notes after both", async () => {
    const { client, pending, resolveAt, result, sent } = open();
    act(() => result.current.check.mutate({ note: 12, id: 31, done: true }));
    act(() => result.current.create.mutate({ text: "Полить цветы" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => resolveAt(sent("POST", "/notes"), 201, { ...note, id: 13, text: "Полить цветы" }));
    await waitFor(() => expect(ids(client)).toEqual([12, 13, 11, 10])); // the newest, under the pinned one
    expect(pending).toHaveLength(2);

    act(() => resolveAt(sent("PATCH", "/notes/12/items/31"), 200, checked));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(pending[2]).toMatchObject({ method: "GET", path: "/notes" });
  });
});
