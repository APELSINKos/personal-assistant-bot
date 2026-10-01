import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { LangProvider } from "../i18n";
import { habit, me, note, scheduleSource } from "../test/fixtures";
import { installTelegram } from "../test/fakeTelegram";
import { mockApi } from "../test/mockApi";
import { ApiError } from "./client";
import type { Agenda, Habit, Me, Note, ScheduleState } from "./types";
import {
  createQueryClient, errorCode, keys, useDeleteNote, useDeleteReminder, useDisconnectSchedule, useHabits,
  useNotes, useRefreshSchedule, useScheduleAlerts, useSetCity, useSetMark, useUpdateMe, useUploadSchedule,
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
  it("doesn't resurrect a row deleted just before another one settles", async () => {
    const client = createQueryClient();
    const noteA = note;
    const noteB: Note = { ...note, id: 12, text: "Вторая заметка" };
    client.setQueryData(keys.notes, [noteA, noteB]);
    const { pending, resolveAt } = controllableFetch();

    const { result } = renderHook(() => ({ del: useDeleteNote(), notes: useNotes() }), {
      wrapper: wrapperFor(client),
    });

    act(() => {
      result.current.del.mutate(noteA.id);
    });
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([noteB]));

    act(() => {
      result.current.del.mutate(noteB.id);
    });
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]));
    expect(pending).toHaveLength(2); // both DELETEs are independent, no shared scope needed

    // The first delete settles while the second is still in flight — must not refetch yet,
    // or a list that hasn't caught up with the second delete would resurrect note B.
    act(() => {
      resolveAt(0, 204, null);
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(pending).toHaveLength(2); // no premature refetch
    expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]);

    act(() => {
      resolveAt(1, 204, null);
    });
    await waitFor(() => expect(pending).toHaveLength(3)); // now the list refetch is allowed
    act(() => {
      resolveAt(2, 200, []);
    });
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([]));
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
