import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Note, NoteItem } from "../api/types";
import { Toasts } from "../components/Toasts";
import type { TgWebApp } from "../telegram";
import { installTelegram } from "../test/fakeTelegram";
import { checklist, note } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi, type ApiCall } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { NoteEditor } from "./NoteEditor";

const GONE = { status: 404, body: { status: 404, code: "not_found", title: "Not found" } };

function renderEditor(path: string) {
  return renderWithApp(<><NoteEditor /><Toasts /></>, { path });
}

/** Whether Telegram's main button («Сохранить») can be pressed now. */
function canSave(app: TgWebApp): boolean | undefined {
  return vi.mocked(app.MainButton.setParams).mock.calls.at(-1)?.[0].is_active;
}

/** Press Telegram's back button: call the handler the screen registered last. */
async function pressBack(app: TgWebApp) {
  const back = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
  await act(async () => back?.());
}

/** Enter in a field: jsdom submits no form on a key, so the form is submitted as Enter would. */
function pressEnter(field: HTMLElement) {
  const form = field.closest("form");
  if (!form) throw new Error("the field is in no form");
  fireEvent.submit(form);
}

/** Requests the test answers by hand, in the order they came. */
function later() {
  const waiting: { body: unknown; answer: (reply: { status?: number; body?: unknown }) => void }[] = [];
  const handler = ({ body }: { body: unknown }) =>
    new Promise((resolve) => waiting.push({ body, answer: resolve }));
  return { waiting, handler };
}

const lists = (calls: ApiCall[]) => calls.filter((call) => call.method === "GET" && call.path === "/notes").length;

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
    await pressBack(app);
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
    mockApi({ "GET /notes": [note], "PATCH /notes/11": GONE });
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
    // Nothing to pin any more: the 📌 is gone with the note.
    expect(screen.queryByRole("button", { name: "Закрепить" })).not.toBeInTheDocument();

    pressMainButton(app);
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
    expect(screen.getByDisplayValue("черновик")).toBeInTheDocument();
  });

  it("counts characters as the server does: a note of 300 emoji from the bot is saved", async () => {
    const app = installTelegram();
    const emoji = "😀".repeat(300);
    const { calls } = mockApi({
      "GET /notes": [{ ...note, text: emoji }],
      "PATCH /notes/11": { ...note, text: `${emoji}!` },
    });
    renderWithApp(<NoteEditor />, { path: "/notes/11" });
    const editor = await screen.findByLabelText("Текст заметки");
    expect(screen.getByText("300/500")).toBeInTheDocument();

    fireEvent.change(editor, { target: { value: "😀".repeat(501) } });
    expect(screen.getByText("501/500")).toBeInTheDocument();
    expect(editor).toHaveAttribute("aria-invalid", "true");
    expect(canSave(app)).toBe(false);

    fireEvent.change(editor, { target: { value: `${emoji}!` } });
    expect(screen.getByText("301/500")).toBeInTheDocument();
    expect(canSave(app)).toBe(true);
    pressMainButton(app);
    await waitFor(() => expect(calls).toContainEqual({ method: "PATCH", path: "/notes/11", body: { text: `${emoji}!` } }));
  });

  it("ties the counter to the field while the text is over the limit, for a screen reader", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note] });
    renderWithApp(<NoteEditor />, { path: "/notes/11" });
    const editor = await screen.findByLabelText("Текст заметки");
    expect(editor).not.toHaveAccessibleDescription();
    fireEvent.change(editor, { target: { value: "я".repeat(501) } });
    expect(editor).toHaveAccessibleDescription("501/500");
    fireEvent.change(editor, { target: { value: "я".repeat(500) } });
    expect(editor).not.toHaveAccessibleDescription();
  });
});

describe("A new note", () => {
  it("collects a checklist's items and its pin, and saves them with the text in one request", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /notes": [], "POST /notes": { status: 201, body: checklist } });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: " Покупки " } });
    const field = screen.getByRole("textbox", { name: "Новый пункт" });
    const add = screen.getByRole("button", { name: "Добавить" });
    expect(add).toBeDisabled();

    fireEvent.change(field, { target: { value: "  молоко\t2 л  " } });
    fireEvent.click(add);
    expect(field).toHaveValue("");
    expect(field).toHaveFocus(); // the next item goes in at once
    fireEvent.change(field, { target: { value: "хлеб" } });
    pressEnter(field);
    fireEvent.change(field, { target: { value: "сыр" } });
    pressEnter(field);
    // Without checks: only «×».
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Удалить пункт «хлеб»" }));
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["молоко 2 л", "сыр"]);

    fireEvent.click(screen.getByRole("button", { name: "Закрепить" }));
    expect(screen.getByRole("button", { name: "Открепить" })).toBeInTheDocument();
    expect(calls.filter((request) => request.method !== "GET")).toEqual([]); // nothing goes before «Сохранить»

    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/notes"));
    expect(calls).toContainEqual({
      method: "POST", path: "/notes", body: { text: "Покупки", items: ["молоко 2 л", "сыр"], pinned: true },
    });
  });

  it("asks for a list's title before it can be saved, and before leaving its items", async () => {
    const app = installTelegram({
      showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(false)),
    });
    mockApi({ "GET /notes": [] });
    const { history } = renderEditor("/notes/new");
    expect(app.enableClosingConfirmation).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Новый пункт" }), { target: { value: "молоко" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));

    expect(screen.getByText("Напиши название списка")).toBeInTheDocument();
    expect(screen.getByLabelText("Текст заметки")).toHaveAccessibleDescription("Напиши название списка");
    expect(canSave(app)).toBe(false);
    expect(app.enableClosingConfirmation).toHaveBeenCalled();
    await pressBack(app);
    expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function));
    expect(history.at(-1)).toBe("/notes/new");

    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "Покупки" } });
    expect(screen.queryByText("Напиши название списка")).not.toBeInTheDocument();
    expect(canSave(app)).toBe(true);
  });

  it("saves an item typed but not added with the note", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /notes": [], "POST /notes": { status: 201, body: checklist } });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "Покупки" } });
    const field = screen.getByRole("textbox", { name: "Новый пункт" });
    fireEvent.change(field, { target: { value: "молоко" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
    fireEvent.change(field, { target: { value: "  хлеб\t " } }); // never added
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/notes"));
    expect(calls).toContainEqual({ method: "POST", path: "/notes", body: { text: "Покупки", items: ["молоко", "хлеб"] } });
  });

  it("leaves out a typed item longer than 100 characters, as the add button would", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /notes": [], "POST /notes": { status: 201, body: checklist } });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "Покупки" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Новый пункт" }), { target: { value: "я".repeat(101) } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/notes"));
    expect(calls).toContainEqual({ method: "POST", path: "/notes", body: { text: "Покупки" } });
  });

  it("leaves out a typed item past the 20th", async () => {
    const app = installTelegram();
    const { calls } = mockApi({ "GET /notes": [], "POST /notes": { status: 201, body: checklist } });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "Поездка" } });
    const field = screen.getByRole("textbox", { name: "Новый пункт" });
    const add = screen.getByRole("button", { name: "Добавить" });
    const twenty = Array.from({ length: 20 }, (_, index) => `пункт ${index + 1}`);
    for (const item of twenty) {
      fireEvent.change(field, { target: { value: item } });
      fireEvent.click(add);
    }
    fireEvent.change(field, { target: { value: "ещё один" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/notes"));
    expect(calls).toContainEqual({ method: "POST", path: "/notes", body: { text: "Поездка", items: twenty } });
  });

  it("asks before leaving an item that is only typed", async () => {
    const app = installTelegram({
      showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(false)),
    });
    mockApi({ "GET /notes": [] });
    const { history } = renderEditor("/notes/new");
    expect(app.enableClosingConfirmation).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Новый пункт" }), { target: { value: "молоко" } });
    expect(app.enableClosingConfirmation).toHaveBeenCalled();
    await pressBack(app);
    expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function));
    expect(history.at(-1)).toBe("/notes/new");
  });

  it("leaves without asking when nothing was typed or added", async () => {
    const app = installTelegram();
    mockApi({ "GET /notes": [] });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Закрепить" }));
    await pressBack(app);
    expect(app.showConfirm).not.toHaveBeenCalled();
    expect(history.at(-1)).toBe("/notes");
  });

  it("adds no item that is empty, longer than 100 characters, or the 21st", async () => {
    installTelegram();
    mockApi({ "GET /notes": [] });
    renderEditor("/notes/new");
    const field = screen.getByRole("textbox", { name: "Новый пункт" });
    const add = screen.getByRole("button", { name: "Добавить" });

    fireEvent.change(field, { target: { value: " \t " } });
    expect(add).toBeDisabled();
    fireEvent.change(field, { target: { value: "😀".repeat(100) } }); // 100 characters, 200 UTF-16 units
    expect(add).toBeEnabled();
    fireEvent.change(field, { target: { value: "😀".repeat(101) } });
    expect(add).toBeDisabled();
    expect(screen.getByText("101/100")).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription("101/100");

    for (let number = 1; number <= 20; number += 1) {
      fireEvent.change(field, { target: { value: `пункт ${number}` } });
      fireEvent.click(add);
    }
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    fireEvent.change(field, { target: { value: "ещё один" } });
    expect(add).toBeDisabled();
    expect(screen.getByText("Не больше 20 пунктов")).toBeInTheDocument();
  });

  it("stays with its text and items when five notes are pinned already", async () => {
    const app = installTelegram();
    mockApi({
      "GET /notes": [],
      "POST /notes": { status: 409, body: { status: 409, code: "limit_reached", entity: "pinned_note", limit: 5 } },
    });
    const { history } = renderEditor("/notes/new");
    fireEvent.change(screen.getByLabelText("Текст заметки"), { target: { value: "Важное" } });
    fireEvent.click(screen.getByRole("button", { name: "Закрепить" }));
    pressMainButton(app);
    expect(await screen.findByText("Закрепить можно не больше 5 заметок — открепи одну")).toBeInTheDocument();
    expect(history.at(-1)).toBe("/notes/new");
    expect(screen.getByDisplayValue("Важное")).toBeInTheDocument();
  });
});

describe("A saved note", () => {
  it("pins at once and puts the pin back when five notes are pinned", async () => {
    installTelegram();
    const patch = later();
    const { calls } = mockApi({ "GET /notes": [note], "PATCH /notes/11": patch.handler });
    renderEditor("/notes/11");
    fireEvent.click(await screen.findByRole("button", { name: "Закрепить" }));
    expect(await screen.findByRole("button", { name: "Открепить" })).toBeInTheDocument();
    await waitFor(() => expect(patch.waiting).toHaveLength(1));
    expect(patch.waiting[0]?.body).toEqual({ pinned: true }); // the pin alone: the text is not touched

    act(() =>
      patch.waiting[0]?.answer({
        status: 409, body: { status: 409, code: "limit_reached", entity: "pinned_note", limit: 5 },
      }),
    );
    expect(await screen.findByText("Закрепить можно не больше 5 заметок — открепи одну")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Закрепить" })).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "PATCH")).toHaveLength(1);
  });

  it("unpins a pinned note", async () => {
    installTelegram();
    let pinned = true;
    const { calls } = mockApi({
      "GET /notes": () => ({ body: [{ ...checklist, pinned }] }),
      "PATCH /notes/12": () => {
        pinned = false;
        return { body: { ...checklist, pinned } };
      },
    });
    renderEditor("/notes/12");
    fireEvent.click(await screen.findByRole("button", { name: "Открепить" }));
    expect(await screen.findByRole("button", { name: "Закрепить" })).toBeInTheDocument();
    await waitFor(() => expect(calls).toContainEqual({ method: "PATCH", path: "/notes/12", body: { pinned: false } }));
    await waitFor(() => expect(lists(calls)).toBe(2));
    expect(screen.getByRole("button", { name: "Закрепить" })).toBeInTheDocument();
  });

  it("lists the addresses of its text under the field, each opening where it leads", async () => {
    const app = installTelegram();
    const text = "Вход: https://example.com/a\nЧат: t.me/durov\nещё раз https://example.com/a";
    mockApi({ "GET /notes": [{ ...note, text }] });
    renderEditor("/notes/11");
    const links = await screen.findByRole("group", { name: "Ссылки" });
    const buttons = within(links).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["https://example.com/a", "t.me/durov"]);
    fireEvent.click(within(links).getByRole("button", { name: "t.me/durov" }));
    expect(app.openTelegramLink).toHaveBeenCalledWith("https://t.me/durov");
    fireEvent.click(within(links).getByRole("button", { name: "https://example.com/a" }));
    expect(app.openLink).toHaveBeenCalledWith("https://example.com/a");
  });

  it("has no line of addresses for a text without any", async () => {
    installTelegram();
    mockApi({ "GET /notes": [note] });
    renderEditor("/notes/11");
    await screen.findByDisplayValue("Купить хлеб");
    expect(screen.queryByRole("group", { name: "Ссылки" })).not.toBeInTheDocument();
  });

  it("checks an item at once, sends quick taps one at a time and asks for the notes after the last", async () => {
    installTelegram();
    const patch = later();
    const { calls } = mockApi({ "GET /notes": [checklist], "PATCH /notes/12/items/31": patch.handler });
    renderEditor("/notes/12");
    const milk = await screen.findByRole("checkbox", { name: "молоко" });
    expect(milk).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "хлеб" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "хлеб" }).closest("li")).toHaveClass("item--done");

    fireEvent.click(milk);
    await waitFor(() => expect(milk).toBeChecked());
    fireEvent.click(milk);
    await waitFor(() => expect(milk).not.toBeChecked());
    await waitFor(() => expect(patch.waiting).toHaveLength(1)); // the second waits for the first
    expect(patch.waiting[0]?.body).toEqual({ done: true });

    act(() => patch.waiting[0]?.answer({ body: { id: 31, text: "молоко", done: true } }));
    await waitFor(() => expect(patch.waiting).toHaveLength(2));
    expect(patch.waiting[1]?.body).toEqual({ done: false });
    expect(milk).not.toBeChecked();
    expect(lists(calls)).toBe(1);

    act(() => patch.waiting[1]?.answer({ body: { id: 31, text: "молоко", done: false } }));
    await waitFor(() => expect(lists(calls)).toBe(2)); // once, after the last
  });

  it("empties the field at once and shows a new item once the server has given it an id", async () => {
    installTelegram();
    const post = later();
    const cheese: NoteItem = { id: 33, text: "сыр", done: false };
    let items = checklist.items;
    mockApi({
      "GET /notes": () => ({ body: [{ ...checklist, items }] }),
      "POST /notes/12/items": async (request: { body: unknown }) => {
        const reply = await post.handler(request);
        items = [...items, cheese];
        return reply;
      },
    });
    renderEditor("/notes/12");
    const field = await screen.findByRole("textbox", { name: "Новый пункт" });
    fireEvent.change(field, { target: { value: "  сыр " } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
    expect(field).toHaveValue("");
    await waitFor(() => expect(post.waiting).toHaveLength(1));
    expect(post.waiting[0]?.body).toEqual({ text: "сыр" });
    // No item without an id: nothing could check it before it exists.
    expect(screen.queryByRole("checkbox", { name: "сыр" })).not.toBeInTheDocument();

    act(() => post.waiting[0]?.answer({ status: 201, body: cheese }));
    expect(await screen.findByRole("checkbox", { name: "сыр" })).not.toBeChecked();
  });

  it("turns «Добавить» off at 20 items, counting those still on their way", async () => {
    installTelegram();
    const nineteen: NoteItem[] = Array.from({ length: 19 }, (_, index) => ({
      id: 100 + index, text: `пункт ${index + 1}`, done: false,
    }));
    const twentieth: NoteItem = { id: 200, text: "двадцатый", done: false };
    let items = nineteen;
    const post = later();
    mockApi({
      "GET /notes": () => ({ body: [{ ...checklist, items }] }),
      "POST /notes/12/items": async (request: { body: unknown }) => {
        const reply = await post.handler(request);
        items = [...items, twentieth];
        return reply;
      },
    });
    renderEditor("/notes/12");
    const field = await screen.findByRole("textbox", { name: "Новый пункт" });
    const add = screen.getByRole("button", { name: "Добавить" });
    fireEvent.change(field, { target: { value: "двадцатый" } });
    fireEvent.click(add);
    fireEvent.change(field, { target: { value: "двадцать первый" } });
    await waitFor(() => expect(add).toBeDisabled()); // the 20th place is taken already
    expect(post.waiting).toHaveLength(1);

    act(() => post.waiting[0]?.answer({ status: 201, body: twentieth }));
    expect(await screen.findByText("Не больше 20 пунктов")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(20);
    expect(add).toBeDisabled();
    expect(field).toHaveValue("двадцать первый"); // kept for when a place frees up
  });

  it("never calls a note of 19 items full while the notes are asked for after an addition", async () => {
    installTelegram();
    const nineteenth: NoteItem = { id: 300, text: "девятнадцатый", done: false };
    let items: NoteItem[] = Array.from({ length: 18 }, (_, index) => ({
      id: 100 + index, text: `пункт ${index + 1}`, done: false,
    }));
    let asked = 0;
    let answerList: (() => void) | undefined;
    mockApi({
      "GET /notes": () => {
        asked += 1;
        const body = [{ ...checklist, items }];
        if (asked === 1) return { body };
        return new Promise((resolve) => (answerList = () => resolve({ body })));
      },
      "POST /notes/12/items": () => {
        items = [...items, nineteenth];
        return { status: 201, body: nineteenth };
      },
    });
    renderEditor("/notes/12");
    const field = await screen.findByRole("textbox", { name: "Новый пункт" });
    const add = screen.getByRole("button", { name: "Добавить" });
    fireEvent.change(field, { target: { value: "девятнадцатый" } });
    fireEvent.click(add);
    expect(await screen.findByRole("checkbox", { name: "девятнадцатый" })).toBeInTheDocument();
    await waitFor(() => expect(answerList).toBeDefined());
    // The notes are still on their way: the item shown no longer counts as on its way as well.
    fireEvent.change(field, { target: { value: "двадцатый" } });
    await waitFor(() => expect(add).toBeEnabled());
    expect(screen.queryByText("Не больше 20 пунктов")).not.toBeInTheDocument();

    act(() => answerList?.());
    await waitFor(() => expect(add).toBeEnabled());
    expect(screen.queryByText("Не больше 20 пунктов")).not.toBeInTheDocument();
  });

  it("says «Этого уже нет» when a checked item is gone, and shows the note as the server has it", async () => {
    installTelegram();
    let asked = 0;
    const bread: NoteItem = { id: 32, text: "хлеб", done: true };
    mockApi({
      "GET /notes": () => {
        asked += 1;
        return { body: [asked === 1 ? checklist : { ...checklist, items: [bread] }] };
      },
      "PATCH /notes/12/items/31": GONE,
    });
    renderEditor("/notes/12");
    fireEvent.click(await screen.findByRole("checkbox", { name: "молоко" }));
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: "молоко" })).not.toBeInTheDocument());
    expect(screen.getByRole("checkbox", { name: "хлеб" })).toBeChecked();
  });

  it("deletes an item and the checked ones without asking", async () => {
    const app = installTelegram();
    let items = checklist.items;
    const { calls } = mockApi({
      "GET /notes": () => ({ body: [{ ...checklist, items }] }),
      "DELETE /notes/12/items/31": () => {
        items = items.filter((item) => item.id !== 31);
        return { status: 204 };
      },
      "DELETE /notes/12/items?done=true": () => {
        items = items.filter((item) => !item.done);
        return { status: 204 };
      },
    });
    renderEditor("/notes/12");
    fireEvent.click(await screen.findByRole("button", { name: "Удалить пункт «молоко»" }));
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: "молоко" })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Убрать отмеченные" }));
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: "хлеб" })).not.toBeInTheDocument());
    // Nothing checked is left: no «Убрать отмеченные» either.
    expect(screen.queryByRole("button", { name: "Убрать отмеченные" })).not.toBeInTheDocument();
    expect(calls).toContainEqual({ method: "DELETE", path: "/notes/12/items/31", body: undefined });
    expect(calls).toContainEqual({ method: "DELETE", path: "/notes/12/items?done=true", body: undefined });
    expect(app.showConfirm).not.toHaveBeenCalled();
  });

  it("opens an address in an item without checking the item", async () => {
    const app = installTelegram();
    const site: Note = { ...checklist, items: [{ id: 31, text: "заказать на https://shop.example/milk", done: false }] };
    const { calls } = mockApi({ "GET /notes": [site] });
    renderEditor("/notes/12");
    const check = await screen.findByRole("checkbox", { name: "заказать на https://shop.example/milk" });
    fireEvent.click(screen.getByRole("button", { name: "https://shop.example/milk" }));
    expect(app.openLink).toHaveBeenCalledWith("https://shop.example/milk");
    // A tap on the text checks nothing either: it is no label.
    fireEvent.click(screen.getByText(/заказать на/));
    expect(check).not.toBeChecked();
    expect(calls.filter((call) => call.method === "PATCH")).toEqual([]);
  });

  it("saves only the text, and asks on leaving only about a text not saved", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /notes": [checklist],
      "PATCH /notes/12/items/31": { id: 31, text: "молоко", done: true },
    });
    const { history } = renderEditor("/notes/12");
    fireEvent.click(await screen.findByRole("checkbox", { name: "молоко" }));
    await waitFor(() => expect(calls).toContainEqual({
      method: "PATCH", path: "/notes/12/items/31", body: { done: true },
    }));
    expect(canSave(app)).toBe(false); // the text is as saved
    expect(app.enableClosingConfirmation).not.toHaveBeenCalled();
    await pressBack(app);
    expect(app.showConfirm).not.toHaveBeenCalled();
    expect(history.at(-1)).toBe("/notes");
  });
});
