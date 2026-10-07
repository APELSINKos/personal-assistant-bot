import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Route, Switch } from "wouter";
import type { Note } from "../api/types";
import { Toasts } from "../components/Toasts";
import { getNotesQuery } from "../lib/notesSearch";
import { installTelegram } from "../test/fakeTelegram";
import { checklist, note } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { NoteEditor } from "./NoteEditor";
import { NotesScreen } from "./Notes";

const call: Note = { ...note, id: 10, text: "Позвонить маме" };
const wifi: Note = { ...note, id: 9, text: "Пароль от WiFi: hunter2" };

/** The list and the editor, as the app routes them, with the toasts. */
function renderNotes(path = "/notes") {
  return renderWithApp(
    <>
      <Switch>
        <Route path="/notes" component={NotesScreen} />
        <Route path="/notes/new" component={NoteEditor} />
        <Route path="/notes/:id" component={NoteEditor} />
      </Switch>
      <Toasts />
    </>,
    { path },
  );
}

/** What the list shows, top to bottom: its headings and its notes. */
function shown(): (string | null)[] {
  return Array.from(document.querySelectorAll("h2, .note-card__text"), (element) => element.textContent);
}

/** A pull down the screen far enough to refresh it. */
function pullDown() {
  const title = screen.getByRole("heading", { level: 1 });
  fireEvent.touchStart(title, { touches: [{ clientX: 100, clientY: 100 }] });
  fireEvent.touchMove(title, { touches: [{ clientX: 100, clientY: 300 }] });
  fireEvent.touchEnd(title);
}

describe("Notes", () => {
  it("lists notes and opens one", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note] });
    const { history } = renderWithApp(<NotesScreen />, { path: "/notes" });
    fireEvent.click(await screen.findByRole("link", { name: "Купить хлеб" }));
    expect(history.at(-1)).toBe("/notes/11");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Заметки 1/50");
  });

  it("puts the pinned notes on top under a heading of their own, a checklist with its progress", async () => {
    installTelegram();
    mockApi({ "GET /notes": [checklist, note, call] });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    const shopping = await screen.findByRole("link", { name: "📌 Покупки Отмечено 1 из 2" });
    expect(shopping).toHaveAttribute("href", "/notes/12");
    expect(screen.getByText("✅ 1/2")).toBeInTheDocument();
    expect(shown()).toEqual(["Закреплённые", "📌 Покупки", "Остальные", "Купить хлеб", "Позвонить маме"]);
  });

  it("gives the notes no headings when none is pinned", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note, call] });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    await screen.findByRole("link", { name: "Купить хлеб" });
    expect(shown()).toEqual(["Купить хлеб", "Позвонить маме"]);
  });

  it("filters as it is typed, by the items too, and says what it found", async () => {
    installTelegram();
    mockApi({ "GET /notes": [checklist, note, wifi] });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    const field = await screen.findByRole("searchbox", { name: "Найти в заметках" });

    fireEvent.change(field, { target: { value: "wifi" } });
    expect(shown()).toEqual(["Пароль от WiFi: hunter2"]);
    expect(screen.getByRole("status")).toHaveTextContent("Найдено заметок: 1");

    fireEvent.change(field, { target: { value: "МОЛОКО" } }); // an item of «Покупки»
    expect(shown()).toEqual(["Закреплённые", "📌 Покупки"]);

    fireEvent.change(field, { target: { value: "хлеб купить" } }); // every word, in any order
    expect(shown()).toEqual(["Купить хлеб"]);

    fireEvent.change(field, { target: { value: "ёлка" } });
    expect(shown()).toEqual([]);
    expect(screen.getByRole("status")).toHaveTextContent("Ничего не нашлось");

    fireEvent.change(field, { target: { value: "   " } });
    expect(shown()).toHaveLength(5);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("keeps the query while a note is open and finds the same notes after it", async () => {
    const app = installTelegram();
    mockApi({ "GET /notes": [checklist, note, wifi] });
    const { history } = renderNotes();
    fireEvent.change(await screen.findByRole("searchbox"), { target: { value: "купить" } });
    fireEvent.click(screen.getByRole("link", { name: "Купить хлеб" }));
    expect(await screen.findByDisplayValue("Купить хлеб")).toBeInTheDocument();
    expect(history.at(-1)).toBe("/notes/11");
    expect(history.join(" ")).not.toContain("?"); // the query is in no address

    const back = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
    act(() => back?.());
    expect(await screen.findByRole("searchbox")).toHaveValue("купить");
    expect(shown()).toEqual(["Купить хлеб"]);
    expect(getNotesQuery()).toBe("купить");
  });

  it("offers no search without notes", async () => {
    installTelegram();
    mockApi({ "GET /notes": [] });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    expect(await screen.findByText("Заметок пока нет. Нажми «+», чтобы создать первую.")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Заметки 0/50");
  });

  it("opens an address in a card, and not the note", async () => {
    const app = installTelegram();
    const text = "Скидки тут (https://example.com/sale). Чат — t.me/x, сайты “https://x.ru” и \"https://y.ru\"";
    mockApi({ "GET /notes": [{ ...note, text }] });
    const { history } = renderWithApp(<NotesScreen />, { path: "/notes" });

    fireEvent.click(await screen.findByRole("button", { name: "https://example.com/sale" }));
    expect(app.openLink).toHaveBeenLastCalledWith("https://example.com/sale"); // without «)» and «.»
    fireEvent.click(screen.getByRole("button", { name: "t.me/x" }));
    expect(app.openTelegramLink).toHaveBeenLastCalledWith("https://t.me/x"); // inside Telegram
    fireEvent.click(screen.getByRole("button", { name: "https://x.ru" }));
    expect(app.openLink).toHaveBeenLastCalledWith("https://x.ru"); // without the quotes
    fireEvent.click(screen.getByRole("button", { name: "https://y.ru" }));
    expect(app.openLink).toHaveBeenLastCalledWith("https://y.ru");
    expect(history).toEqual(["/notes"]);

    // The text loses nothing around them, and the card still opens the note.
    expect(shown()).toEqual([text]);
    fireEvent.click(screen.getByRole("link", { name: /^Скидки тут/ }));
    expect(history.at(-1)).toBe("/notes/11");
  });

  it("brings a card back to its first lines once the keyboard's focus leaves its text", async () => {
    // Addresses past the sixth line: the browser scrolls the clamped text to show a focused one.
    installTelegram();
    const text = `${"Строка\n".repeat(8)}https://example.com/a https://example.com/b`;
    mockApi({ "GET /notes": [{ ...note, text }, call] });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    const first = await screen.findByRole("button", { name: "https://example.com/a" });
    const paragraph = first.closest("p") as HTMLParagraphElement;
    Object.defineProperty(paragraph, "scrollTop", { value: 0, writable: true });

    act(() => first.focus());
    paragraph.scrollTop = 120;
    act(() => screen.getByRole("button", { name: "https://example.com/b" }).focus());
    expect(paragraph.scrollTop).toBe(120); // still inside the text: the next address shows
    act(() => screen.getByRole("searchbox").focus());
    expect(paragraph.scrollTop).toBe(0); // the focus has left: the card starts at the top again
  });

  it("dims «+» at 50 notes and says why instead of opening a new note", async () => {
    const app = installTelegram();
    const fifty = Array.from({ length: 50 }, (_, index) => ({ ...note, id: index + 1, text: `Заметка ${index + 1}` }));
    mockApi({ "GET /notes": fifty });
    const { history } = renderNotes();
    const plus = await screen.findByRole("link", { name: "Добавить заметку" });
    expect(plus).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Заметки 50/50");
    fireEvent.click(plus);
    expect(await screen.findByText("Достигнут лимит — 50 заметок. Удали лишние.")).toBeInTheDocument();
    expect(history).toEqual(["/notes"]);
    expect(app.HapticFeedback?.notificationOccurred).toHaveBeenCalledWith("error");
  });

  it("opens a new note from «+» below the limit", async () => {
    installTelegram();
    const many = Array.from({ length: 49 }, (_, index) => ({ ...note, id: index + 1, text: `Заметка ${index + 1}` }));
    mockApi({ "GET /notes": many });
    const { history } = renderNotes();
    const plus = await screen.findByRole("link", { name: "Добавить заметку" });
    expect(plus).not.toHaveAttribute("aria-disabled");
    fireEvent.click(plus);
    expect(await screen.findByRole("heading", { name: "Новая заметка" })).toBeInTheDocument();
    expect(history.at(-1)).toBe("/notes/new");
  });

  it("keeps the notes shown when a refresh fails, and shows fresh ones after a refresh that works", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    installTelegram();
    let reply: unknown = { body: [note] };
    mockApi({ "GET /notes": () => reply });
    renderWithApp(<NotesScreen />, { path: "/notes" });
    await screen.findByRole("link", { name: "Купить хлеб" });
    const settle = () => act(() => vi.advanceTimersByTimeAsync(5_000));

    reply = { status: 503, body: { status: 503, code: "upstream_unavailable", title: "Unavailable" } };
    pullDown();
    await settle();
    expect(screen.getByRole("link", { name: "Купить хлеб" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();

    reply = { body: [call, note] };
    pullDown();
    await settle();
    expect(shown()).toEqual(["Позвонить маме", "Купить хлеб"]);
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
