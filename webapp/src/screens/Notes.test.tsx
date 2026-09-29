import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { note } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { NoteEditor } from "./NoteEditor";
import { NotesScreen } from "./Notes";

describe("Notes", () => {
  it("lists notes and opens one", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note] });
    const { history } = renderWithApp(<NotesScreen />, { path: "/notes" });
    fireEvent.click(await screen.findByText("Купить хлеб"));
    expect(history.at(-1)).toBe("/notes/11");
  });

  it("test_deleting_a_note_that_is_already_gone", async () => {
    installTelegram();
    let listed = [note];
    let answerRefetch: (() => void) | undefined;
    mockApi({
      "GET /notes": () => {
        if (listed.length > 0) return { body: listed };
        // The list asked for after the delete answers late; meanwhile the row must stay gone.
        return new Promise((resolve) => (answerRefetch = () => resolve({ body: listed })));
      },
      "DELETE /notes/11": () => {
        listed = []; // it was deleted in the bot a moment ago
        return { status: 404, body: { status: 404, code: "not_found", title: "Not found" } };
      },
    });
    renderWithApp(<><NotesScreen /><Toasts /></>, { path: "/notes" });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить заметку" }));
    await waitFor(() => expect(screen.queryByText("Купить хлеб")).not.toBeInTheDocument());
    // From here on the row must never come back, not even for a frame.
    let reappeared = false;
    const watcher = new MutationObserver(() => {
      if (screen.queryByText("Купить хлеб")) reappeared = true;
    });
    watcher.observe(document.body, { childList: true, subtree: true, characterData: true });
    try {
      expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
      await waitFor(() => expect(answerRefetch).toBeDefined());
      await new Promise((resolve) => setTimeout(resolve, 20)); // let every pending render land
      expect(screen.queryByText("Купить хлеб")).not.toBeInTheDocument();
      act(() => answerRefetch?.());
      expect(await screen.findByText(/Заметок пока нет/)).toBeInTheDocument();
    } finally {
      watcher.disconnect();
    }
    expect(reappeared).toBe(false);
  });
});

describe("NoteEditor", () => {
  it("edits a note and saves with the main button", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /notes": [note],
      "PATCH /notes/11": { ...note, text: "Купить молоко" },
    });
    const { history } = renderWithApp(<NoteEditor />, { path: "/notes/11" });
    const editor = await screen.findByDisplayValue("Купить хлеб");
    fireEvent.change(editor, { target: { value: "Купить молоко" } });
    expect(screen.getByText("13/500")).toBeInTheDocument();
    expect(app.enableClosingConfirmation).toHaveBeenCalled();
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/notes"));
    expect(calls).toContainEqual({ method: "PATCH", path: "/notes/11", body: { text: "Купить молоко" } });
  });

  it("creates a new note", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /notes": [], "POST /notes": () => ({ status: 201, body: note }) });
    renderWithApp(<NoteEditor />, { path: "/notes/new" });
    fireEvent.change(await screen.findByLabelText("Текст заметки"), { target: { value: "Купить хлеб" } });
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "POST", path: "/notes", body: { text: "Купить хлеб" } }),
    );
  });

  it("asks before leaving with unsaved edits", async () => {
    const app = installTelegram({
      showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(false)),
    });
    mockApi({ "GET /notes": [note] });
    const { history } = renderWithApp(<NoteEditor />, { path: "/notes/11" });
    fireEvent.change(await screen.findByDisplayValue("Купить хлеб"), { target: { value: "черновик" } });
    const back = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
    await act(async () => back?.());
    expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function));
    expect(history.at(-1)).toBe("/notes/11");
  });

  it("shows a not-found state for a note that doesn't exist", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note] });
    renderWithApp(<NoteEditor />, { path: "/notes/999" });
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Заметки" })).toBeInTheDocument();
  });

  it("keeps the draft when the note disappears elsewhere while editing", async () => {
    const app = installTelegram();
    mockApi({
      "GET /notes": [note],
      "PATCH /notes/11": () => ({ status: 404, body: { status: 404, code: "not_found", title: "Not found" } }),
    });
    const { client } = renderWithApp(<><NoteEditor /><Toasts /></>, { path: "/notes/11" });
    const editor = await screen.findByDisplayValue("Купить хлеб");
    fireEvent.change(editor, { target: { value: "черновик" } });

    // The note is gone from the cache — e.g. deleted in another tab — while the user is still
    // editing it here. React Query notifies subscribers on a real macrotask (`setTimeout(…, 0)`),
    // so the update is awaited here to let the screen actually re-render before the assertion.
    await act(async () => {
      client.setQueryData(["notes"], []);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.getByDisplayValue("черновик")).toBeInTheDocument();

    pressMainButton(app);
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
    expect(screen.getByDisplayValue("черновик")).toBeInTheDocument();
  });
});
