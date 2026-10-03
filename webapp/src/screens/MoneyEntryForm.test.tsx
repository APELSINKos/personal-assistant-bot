import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { keys } from "../api/queries";
import type { TgWebApp } from "../telegram";
import { installTelegram } from "../test/fakeTelegram";
import { me, moneyCategories } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoneyEntryForm } from "./MoneyEntryForm";

const ENTRY = { id: 24, amount: 43050, category_id: 2, note: "кофе", day: "2026-09-28" };
const SAVED = { entry: ENTRY, alerts: [] };
const AMOUNT_HINT = "Сумма — число больше нуля, не больше двух знаков после запятой";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-28T09:00:00Z")); // noon in Moscow
});

function open(path: string, routes: Record<string, unknown> = {}, app: TgWebApp = installTelegram()) {
  const api = mockApi({ "GET /me": me, "GET /money/categories": moneyCategories, ...routes });
  return { app, ...api, ...renderWithApp(<MoneyEntryForm />, { path }) };
}

/** Whether Telegram's main button can be pressed now. */
function active(app: TgWebApp) {
  return vi.mocked(app.MainButton.setParams).mock.calls.at(-1)?.[0].is_active;
}

describe("Entry form", () => {
  it("notes an expense: an amount, a category, a note, today", async () => {
    const { app, calls, history } = open("/money/new", { "POST /money/entries": { status: 201, body: SAVED } });
    expect(await screen.findByRole("heading", { name: "Новая запись" })).toBeInTheDocument();
    expect(active(app)).toBe(false);
    fireEvent.change(screen.getByLabelText("Сумма"), { target: { value: "430,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Кафе" }));
    fireEvent.change(screen.getByLabelText("Заметка"), { target: { value: " кофе " } });
    expect(screen.getByLabelText("День")).toHaveValue("2026-09-28");
    expect(active(app)).toBe(true);
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money"));
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({
      amount: "430.50", category_id: 2, note: "кофе", day: "2026-09-28",
    });
  });

  it("explains a wrong amount and offers only the visible categories of the kind", async () => {
    const { app } = open("/money/new");
    fireEvent.change(await screen.findByLabelText("Сумма"), { target: { value: "12,345" } });
    expect(screen.getByText(AMOUNT_HINT)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Продукты" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Одежда" })).not.toBeInTheDocument(); // hidden
    fireEvent.click(screen.getByRole("button", { name: "Продукты" }));
    fireEvent.click(screen.getByRole("button", { name: "Доход" }));
    expect(screen.getByRole("button", { name: "Стипендия" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("button", { name: "Продукты" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Сумма"), { target: { value: "5000" } });
    expect(screen.queryByText(AMOUNT_HINT)).not.toBeInTheDocument();
    expect(active(app)).toBe(false); // the expense category went with the expense
  });

  it("keeps the draft when a refresh in the background fails", async () => {
    const { client } = open("/money/new");
    fireEvent.change(await screen.findByLabelText("Сумма"), { target: { value: "250" } });
    mockApi({ "GET /me": { status: 429, body: { status: 429, code: "rate_limited" } } });
    await act(async () => {
      await client.refetchQueries({ queryKey: keys.me });
      await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
    });
    expect(client.getQueryState(keys.me)?.status).toBe("error");
    expect(screen.getByLabelText("Сумма")).toHaveValue("250");
  });

  it("steps the day back, never past today, and refuses a day over a year back", async () => {
    open("/money/new");
    const day = await screen.findByLabelText("День");
    expect(screen.getByRole("button", { name: "Следующий день" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Предыдущий день" }));
    expect(day).toHaveValue("2026-09-27");
    fireEvent.change(day, { target: { value: "2025-09-26" } }); // 367 days back
    expect(screen.getByText("День — не позже сегодняшнего и не раньше, чем год назад")).toBeInTheDocument();
  });

  it("changes an entry, sending what changed, and keeps an old entry's day", async () => {
    const old = { ...ENTRY, day: "2025-06-01" }; // further back than a new entry may be
    const { app, calls, history } = open("/money/24/edit", {
      "GET /money/entries/24": old, "PATCH /money/entries/24": SAVED,
    });
    expect(await screen.findByLabelText("Сумма")).toHaveValue("430,50");
    expect(screen.getByRole("heading", { name: "Запись" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Кафе" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Сумма"), { target: { value: "450" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money"));
    expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ amount: "450" });
  });

  it("sends nothing when nothing changed", async () => {
    const { app, calls, history } = open("/money/24/edit", { "GET /money/entries/24": ENTRY });
    expect(await screen.findByLabelText("Сумма")).toHaveValue("430,50");
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/money"));
    expect(calls.some((call) => call.method === "PATCH")).toBe(false);
  });

  it("keeps an entry's own hidden category on offer after another is picked", async () => {
    open("/money/25/edit", { "GET /money/entries/25": { ...ENTRY, id: 25, category_id: 5 } });
    expect(await screen.findByRole("button", { name: /Одежда/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Кафе" }));
    expect(screen.getByRole("button", { name: /Одежда/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("deletes an entry after a confirmation", async () => {
    const { app, calls, history } = open("/money/24/edit", {
      "GET /money/entries/24": ENTRY, "DELETE /money/entries/24": { status: 204 },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить запись" }));
    await waitFor(() => expect(history.at(-1)).toBe("/money"));
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить запись?", expect.any(Function));
    await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
  });

  it("says when the entry is gone, and leads back", async () => {
    open("/money/24/edit", { "GET /money/entries/24": { status: 404, body: { status: 404, code: "not_found" } } });
    expect(await screen.findByText("Этой записи уже нет.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "К деньгам" })).toHaveAttribute("href", "/money");
  });

  it("asks before leaving with an unsaved amount", async () => {
    const app = installTelegram({ showConfirm: vi.fn((_m: string, callback: (ok: boolean) => void) => callback(false)) });
    const { history } = open("/money/new", {}, app);
    fireEvent.change(await screen.findByLabelText("Сумма"), { target: { value: "250" } });
    vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0]();
    await waitFor(() => expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function)));
    expect(history.at(-1)).toBe("/money/new");
  });
});
