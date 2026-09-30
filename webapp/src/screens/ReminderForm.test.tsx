import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Reminder } from "../api/types";
import { Toasts } from "../components/Toasts";
import { BOT_CHAT_URL } from "../lib/links";
import { installTelegram } from "../test/fakeTelegram";
import { me, reminder } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { ReminderForm } from "./ReminderForm";

const created: Reminder = { ...reminder, id: 9 };

function at(iso: string) {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(iso));
}

afterEach(() => vi.useRealTimers());

async function ready(client: { getQueryData: (key: string[]) => unknown }) {
  await waitFor(() => expect(client.getQueryData(["me"])).toBeDefined());
}

describe("ReminderForm", () => {
  it("creates a one-off on the day from the path", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "POST /reminders": () => ({ status: 201, body: created }) });
    const { history, client } = renderWithApp(<><ReminderForm /><Toasts /></>, { path: "/calendar/new/2026-09-30" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "10:00" } });
    expect(screen.getByLabelText("Дата")).toHaveValue("2026-09-30");
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/calendar"));
    expect(calls).toContainEqual({
      method: "POST", path: "/reminders", body: { text: "Врач", due_local: "2026-09-30T10:00" },
    });
    expect(await screen.findByText("Напомню!")).toBeInTheDocument();
  });

  it("fills the form from a phrase", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "POST /reminders/parse": {
        text: "зарядка", repeat: "weekly", date: null, time: "07:30", weekdays: 31,
        interval_weeks: 1, month_day: null, description: "по будням в 07:30",
      },
      "POST /reminders": () => ({ status: 201, body: created }),
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "по будням в 7:30 зарядка" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Понять" }));
    await waitFor(() => expect(screen.getByLabelText("О чём напомнить")).toHaveValue("зарядка"));
    expect(screen.getByRole("button", { name: "По будням" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Время")).toHaveValue("07:30");
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST", path: "/reminders",
        body: { text: "зарядка", rule: { repeat: "weekly", time_local: "07:30", weekdays: 31 } },
      }),
    );
  });

  it("builds a repeat on chosen days and a monthly one", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "POST /reminders": () => ({ status: 201, body: created }) });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Пара" } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "10:40" } });
    fireEvent.click(screen.getByRole("button", { name: "Дни недели" }));
    fireEvent.click(screen.getByRole("button", { name: "вт" })); // on by default: today, Tuesday → off
    fireEvent.click(screen.getByRole("button", { name: "ср" }));
    fireEvent.click(screen.getByRole("button", { name: "пт" }));
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST", path: "/reminders",
        body: { text: "Пара", rule: { repeat: "weekly", time_local: "10:40", weekdays: 4 | 16 } },
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Каждый месяц" }));
    fireEvent.change(screen.getByLabelText("Число месяца"), { target: { value: "5" } });
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST", path: "/reminders",
        body: { text: "Пара", rule: { repeat: "monthly", time_local: "10:40", month_day: 5 } },
      }),
    );
  });

  it("edits an existing repeat", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const series: Reminder = {
      ...reminder, id: 2, text: "Зарядка", due_local: "2026-09-30T07:30", repeat: "weekly",
      rule: { repeat: "weekly", time_local: "07:30", weekdays: 31, interval_weeks: 1, month_day: null, anchor_date: "2026-09-28" },
      description: "по будням в 07:30",
    };
    const { calls } = mockApi({
      "GET /me": me,
      "GET /reminders": [series],
      "PATCH /reminders/2": { ...series, rule: { ...series.rule!, time_local: "08:00" } },
    });
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/2" });
    await ready(client);
    expect(await screen.findByDisplayValue("Зарядка")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "По будням" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "08:00" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/calendar"));
    expect(calls).toContainEqual({
      method: "PATCH", path: "/reminders/2",
      body: { text: "Зарядка", rule: { repeat: "weekly", time_local: "08:00", weekdays: 31 } },
    });
  });

  it("test_write_access_refused_creates_nothing", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram({ requestWriteAccess: vi.fn((callback?: (ok: boolean) => void) => callback?.(false)) });
    const { calls } = mockApi({ "GET /me": { ...me, can_write: false } });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    pressMainButton(app);
    expect(await screen.findByText("Разрешить боту писать?")).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "POST")).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Открыть чат с ботом" }));
    expect(app.openTelegramLink).toHaveBeenCalledWith(BOT_CHAT_URL);
  });

  it("records a granted permission before saving", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": { ...me, can_write: false },
      "POST /me/write-access": { ...me, can_write: true },
      "POST /reminders": () => ({ status: 201, body: created }),
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    pressMainButton(app);
    await waitFor(() =>
      expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual(
        expect.arrayContaining(["POST /me/write-access", "POST /reminders"]),
      ),
    );
  });

  it("asks before leaving with changes", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram({ showConfirm: vi.fn((_m: string, callback: (ok: boolean) => void) => callback(false)) });
    mockApi({ "GET /me": me });
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "черновик" } });
    const back = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
    await act(async () => back?.());
    expect(app.showConfirm).toHaveBeenCalledWith("Выйти без сохранения?", expect.any(Function));
    expect(history.at(-1)).toBe("/calendar/new");
  });

  it("shows its own message for a phrase that is too long", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "POST /reminders/parse": () => ({
        status: 422,
        body: { status: 422, code: "validation_error", title: "x", field: "text", reason: "length" },
      }),
    });
    const { client } = renderWithApp(<><ReminderForm /><Toasts /></>, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "очень длинная фраза" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Понять" }));
    expect(await screen.findByText("Слишком длинный текст — сократи")).toBeInTheDocument();
  });
});
