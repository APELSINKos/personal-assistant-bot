import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { LangProvider } from "../i18n";
import { habit, note } from "../test/fixtures";
import { installTelegram } from "../test/fakeTelegram";
import { mockApi } from "../test/mockApi";
import type { Habit, Note } from "./types";
import {
  createQueryClient, keys, useDeleteNote, useHabits, useNotes, useSetCity, useSetMark,
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
      resolveAt(0, 404, { status: 404, code: "not_found", title: "Not found" });
    });

    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
    await waitFor(() => expect(client.getQueryData<Note[]>(keys.notes)).toEqual([note]));
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
  });
});
