import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Reminder } from "../api/types";
import { Toasts } from "../components/Toasts";
import { getCalendarDay } from "../lib/calendarDay";
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
    fireEvent.click(screen.getByRole("button", { name: "вторник" })); // on by default: today, Tuesday → off
    fireEvent.click(screen.getByRole("button", { name: "среда" }));
    fireEvent.click(screen.getByRole("button", { name: "пятница" }));
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
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/calendar"));
    const posts = calls.filter((call) => call.method === "POST").map((call) => call.path);
    expect(posts).toEqual(["/me/write-access", "/reminders"]);
  });

  it("stops without creating anything when granting write access fails", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": { ...me, can_write: false },
      "POST /me/write-access": () => ({ status: 500, body: { status: 500, code: "generic", title: "x" } }),
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    pressMainButton(app);
    await waitFor(() => expect(calls).toContainEqual({ method: "POST", path: "/me/write-access", body: undefined }));
    expect(calls.filter((call) => call.method === "POST" && call.path === "/reminders")).toEqual([]);
  });

  it("does nothing when an old Telegram can't ask for write access", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram({}, "6.5");
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

  it("leaves without asking when nothing changed", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    mockApi({ "GET /me": me });
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    const back = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
    await act(async () => back?.());
    expect(app.showConfirm).not.toHaveBeenCalled();
    expect(history.at(-1)).toBe("/calendar");
  });

  it("lets the day-of-month field be cleared and retyped", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "POST /reminders": () => ({ status: 201, body: created }) });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Зарплата" } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Каждый месяц" }));
    const monthDay = screen.getByLabelText("Число месяца");
    fireEvent.change(monthDay, { target: { value: "" } });
    expect(monthDay).toHaveValue(null); // truly empty, not reverted to 1
    pressMainButton(app);
    expect(calls.filter((call) => call.method === "POST")).toEqual([]); // Save stays off while empty
    fireEvent.change(monthDay, { target: { value: "5" } });
    expect(monthDay).toHaveValue(5); // not "15" from appending onto a leftover "1"
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST", path: "/reminders",
        body: { text: "Зарплата", rule: { repeat: "monthly", time_local: "09:00", month_day: 5 } },
      }),
    );
  });

  it("asks for a time when the phrase doesn't have one", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "POST /reminders/parse": {
        text: "купить молоко", repeat: "none", date: "2026-09-30", time: null,
        weekdays: null, interval_weeks: 1, month_day: null, description: null,
      },
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "завтра купить молоко" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Понять" }));
    await waitFor(() => expect(screen.getByLabelText("О чём напомнить")).toHaveValue("купить молоко"));
    expect(screen.getByLabelText("Время")).toHaveValue("");
    expect(screen.getByLabelText("Время")).toHaveFocus();
    expect(screen.getByText("Укажи время")).toBeInTheDocument();
    pressMainButton(app);
    expect(calls.filter((call) => call.method === "POST" && call.path === "/reminders")).toEqual([]);
  });

  it("names the day toggles in full in English", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({ "GET /me": { ...me, language: "en" } });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new", lang: "en" });
    await ready(client);
    fireEvent.click(screen.getByRole("button", { name: "Days of the week" }));
    const group = screen.getByRole("group", { name: "Days of the week" });
    expect(within(group).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    ]);
  });

  it("keeps the typed text when the phrase has none and fills the rest", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "POST /reminders/parse": {
        text: "", repeat: "none", date: "2026-09-30", time: "09:00",
        weekdays: null, interval_weeks: 1, month_day: null, description: null,
      },
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "завтра в 9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Понять" }));
    await waitFor(() => expect(screen.getByLabelText("Время")).toHaveValue("09:00"));
    expect(screen.getByLabelText("Дата")).toHaveValue("2026-09-30");
    expect(screen.getByLabelText("О чём напомнить")).toHaveValue("Врач");
  });

  it("shows the first day of an every-other-week phrase", async () => {
    at("2026-09-28T12:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "POST /reminders/parse": {
        text: "практика", repeat: "weekly", date: "2026-09-30", time: "09:00", weekdays: 4,
        interval_weeks: 2, month_day: null, description: "раз в две недели по средам в 09:00",
      },
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "раз в две недели по средам в 9 практика" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Понять" }));
    await waitFor(() => expect(screen.getByLabelText("Первый раз")).toHaveValue("2026-09-30"));
    expect(screen.getByRole("button", { name: "Раз в 2 недели" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps typed changes and shows progress while «Понять» is pending", async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    let resolveParse!: (value: { body: unknown }) => void;
    mockApi({
      "GET /me": me,
      "POST /reminders/parse": () => new Promise((resolve) => (resolveParse = resolve)),
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("Напиши, например: завтра в 9 купить молоко"), {
      target: { value: "каждый день зарядка в 7" },
    });
    const understand = screen.getByRole("button", { name: "Понять" });
    fireEvent.click(understand);
    await waitFor(() => expect(understand).toBeDisabled());
    expect(understand).toHaveAttribute("aria-busy", "true");
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "зарядка и растяжка" } });
    act(() => {
      resolveParse({
        body: {
          text: "", repeat: "daily", date: null, time: "07:00", weekdays: null,
          interval_weeks: 1, month_day: null, description: "каждый день в 07:00",
        },
      });
    });
    await waitFor(() => expect(screen.getByLabelText("Время")).toHaveValue("07:00"));
    expect(screen.getByLabelText("О чём напомнить")).toHaveValue("зарядка и растяжка");
  });

  it("remembers the day it just saved for the calendar", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const saved: Reminder = { ...reminder, id: 9, due_local: "2026-10-06T09:00" };
    mockApi({ "GET /me": me, "POST /reminders": () => ({ status: 201, body: saved }) });
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/new/2026-10-06" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Врач" } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "09:00" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/calendar"));
    expect(getCalendarDay()).toBe("2026-10-06");
  });

  it("builds a biweekly repeat and needs a day and a first date", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const { calls } = mockApi({ "GET /me": me, "POST /reminders": () => ({ status: 201, body: created }) });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "Стрижка" } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "18:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Раз в 2 недели" }));
    expect(screen.getByText("Первый раз")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "вторник" })); // clears the default (today)
    expect(screen.getByText("Выбери хотя бы один день")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "четверг" }));
    fireEvent.change(screen.getByLabelText("Первый раз"), { target: { value: "" } });
    pressMainButton(app);
    expect(calls.filter((call) => call.method === "POST")).toEqual([]); // no first date yet
    fireEvent.change(screen.getByLabelText("Первый раз"), { target: { value: "2026-10-01" } });
    pressMainButton(app);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST", path: "/reminders",
        body: {
          text: "Стрижка",
          rule: { repeat: "weekly", time_local: "18:00", weekdays: 8, interval_weeks: 2, anchor_date: "2026-10-01" },
        },
      }),
    );
  });

  it("edits a one-off without turning it into a repeat", async () => {
    at("2026-09-29T09:00:00Z");
    const app = installTelegram();
    const oneOff: Reminder = { ...reminder, id: 4, text: "Стоматолог", due_local: "2026-10-02T15:00" };
    const { calls } = mockApi({
      "GET /me": me,
      "GET /reminders": [oneOff],
      "PATCH /reminders/4": { ...oneOff, due_local: "2026-10-02T16:00" },
    });
    const { history, client } = renderWithApp(<ReminderForm />, { path: "/calendar/4" });
    await ready(client);
    expect(await screen.findByDisplayValue("Стоматолог")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "16:00" } });
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/calendar"));
    expect(calls).toContainEqual({
      method: "PATCH", path: "/reminders/4",
      body: { text: "Стоматолог", due_local: "2026-10-02T16:00" },
    });
  });

  it('shows the error state when the reminders query fails, not "not found"', async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /reminders": { status: 500, body: { status: 500, code: "generic", title: "Oops" } },
    });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/4" });
    await ready(client);
    // Unlike the calendar's agenda query, `useReminders()` has no `enabled` gate, so it starts
    // fetching (and, on failure, retrying) on the very first render — before a `setQueryDefaults`
    // call after `renderWithApp` could reach it. Outlasting the real retry backoff is simpler.
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("Этого уже нет")).not.toBeInTheDocument();
  }, 8000);

  it('shows "Этого уже нет" only when the id truly doesn\'t exist', async () => {
    at("2026-09-29T09:00:00Z");
    installTelegram();
    mockApi({ "GET /me": me, "GET /reminders": [reminder] }); // no reminder with id 999
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/999" });
    await ready(client);
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
  });

  it("rolls the default date and time past midnight", async () => {
    at("2026-09-29T20:50:00Z"); // 23:50 in Moscow
    installTelegram();
    mockApi({ "GET /me": me });
    const { client } = renderWithApp(<ReminderForm />, { path: "/calendar/new" });
    await ready(client);
    expect(screen.getByLabelText("Дата")).toHaveValue("2026-09-30");
    expect(screen.getByLabelText("Время")).toHaveValue("00:00");
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
