import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { keys } from "../api/queries";
import type { HabitDetail } from "../api/types";
import { Toasts } from "../components/Toasts";
import { withMark } from "../lib/habits";
import { installTelegram } from "../test/fakeTelegram";
import { habit, me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { RATE_LIMITED, refresh } from "../test/refresh";
import { renderWithApp } from "../test/render";
import { HabitScreen } from "./Habit";

// Created on Monday 14 September 2026; done every day but Sunday 20th (missed) and Thursday
// 1 October (no mark); today is Friday 2 October, Saturday and Sunday are ahead.
const PATTERN = "111111" + "0" + "1111111111" + "-" + "1";
const DETAIL: HabitDetail = {
  ...habit,
  created_on: "2026-09-14",
  year_from: "2025-09-29",
  year: ".".repeat(350) + PATTERN + "..",
};

function show(detail: HabitDetail | { status: number; body: unknown } = DETAIL, lang: "ru" | "en" = "ru") {
  const api = mockApi({ "GET /me": me, "GET /habits/7": detail });
  const view = renderWithApp(
    <>
      <HabitScreen />
      <Toasts />
    </>,
    { path: "/habits/7", lang },
  );
  return { ...api, ...view };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-02T09:00:00Z")); // noon in Moscow
  installTelegram();
});

describe("Habit screen", () => {
  it("offers a retry instead of an endless wait when the user cannot be read", async () => {
    const { calls } = mockApi({ "GET /me": { status: 404, body: { status: 404, code: "not_found" } }, "GET /habits/7": DETAIL });
    renderWithApp(<HabitScreen />, { path: "/habits/7" });
    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
    expect(calls.map((call) => call.path)).toContain("/me");
  });

  it("shows the habit, its tiles, its year and this month", async () => {
    show();
    expect(await screen.findByRole("heading", { level: 1, name: "Спорт" })).toBeInTheDocument();
    expect(screen.getByText("Каждый день · с 14 сентября")).toBeInTheDocument();
    expect(screen.getByText("5 дней")).toBeInTheDocument(); // the streak
    expect(screen.getByText("9 дней")).toBeInTheDocument(); // the record
    expect(screen.getByText("71%")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Показать месяц недели/ })).toHaveLength(53);
    expect(screen.getByRole("heading", { name: "Октябрь 2026" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 октября: без отметки. Нажми, чтобы изменить" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2 октября: выполнено. Нажми, чтобы изменить" })).toHaveAttribute(
      "aria-current",
      "date",
    );
    expect(screen.queryByRole("button", { name: /^3 октября/ })).not.toBeInTheDocument(); // ahead
  });

  it("marks a day of the month with a tap", async () => {
    show();
    let year = DETAIL.year;
    const { calls } = mockApi({
      "GET /me": me,
      "GET /habits/7": () => ({ body: { ...DETAIL, year } }),
      "PUT /habits/7/marks/2026-10-01": ({ body }: { body: unknown }) => {
        year = withMark(DETAIL.year_from, year, "2026-10-01", (body as { done: boolean | null }).done);
        return { body: habit };
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "1 октября: без отметки. Нажми, чтобы изменить" }));
    expect(await screen.findByRole("button", { name: "1 октября: выполнено. Нажми, чтобы изменить" })).toBeInTheDocument();
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-10-01", body: { done: true } }),
    );
  });

  it("marks the day a tap is on, even when the tap comes after midnight", async () => {
    vi.setSystemTime(new Date("2026-10-02T20:59:30Z")); // 23:59:30 on 2 October in Moscow
    show();
    const { calls } = mockApi({ "GET /me": me, "GET /habits/7": DETAIL, "PUT /habits/7/marks/2026-10-02": habit });
    const shown = await screen.findByRole("button", { name: "2 октября: выполнено. Нажми, чтобы изменить" });
    vi.setSystemTime(new Date("2026-10-02T21:00:30Z")); // 00:00:30 on 3 October
    fireEvent.click(shown);
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-10-02", body: { done: false } }),
    );
  });

  it("moves between months within the habit's life", async () => {
    show();
    const previous = await screen.findByRole("button", { name: "Предыдущий месяц" });
    const next = screen.getByRole("button", { name: "Следующий месяц" });
    expect(next).toBeDisabled(); // nothing to mark ahead of today's month
    fireEvent.click(previous);
    expect(screen.getByRole("heading", { name: "Сентябрь 2026" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20 сентября: пропущено. Нажми, чтобы изменить" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^13 сентября/ })).not.toBeInTheDocument(); // before the habit
    expect(previous).toBeDisabled(); // the habit began in September
    fireEvent.click(next);
    expect(screen.getByRole("heading", { name: "Октябрь 2026" })).toBeInTheDocument();
  });

  it("opens the month of a week tapped on the year map", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Показать месяц недели 14 сент. – 20 сент." }));
    expect(screen.getByRole("heading", { name: "Сентябрь 2026" })).toBeInTheDocument();
  });

  it("opens this month for this week, and never a month before the habit", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Показать месяц недели 14 сент. – 20 сент." }));
    fireEvent.click(screen.getByRole("button", { name: "Показать месяц недели 28 сент. – 4 окт." }));
    expect(screen.getByRole("heading", { name: "Октябрь 2026" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать месяц недели 24 авг. – 30 авг." }));
    expect(screen.getByRole("heading", { name: "Сентябрь 2026" })).toBeInTheDocument();
  });

  it("shares the card through Telegram, or has the bot send it", async () => {
    const app = installTelegram();
    const first = show();
    first.calls.length = 0;
    mockApi({ "GET /me": me, "GET /habits/7": DETAIL, "POST /habits/7/share": { prepared_id: "prepared-1" } });
    fireEvent.click(await screen.findByRole("button", { name: "Поделиться" }));
    await waitFor(() => expect(app.shareMessage).toHaveBeenCalledWith("prepared-1", expect.any(Function)));
    first.unmount();

    installTelegram({}, "7.10");
    show();
    mockApi({ "GET /me": me, "GET /habits/7": DETAIL, "POST /habits/7/card": { status: 204 } });
    fireEvent.click(await screen.findByRole("button", { name: "Поделиться" }));
    expect(await screen.findByText("Карточка в чате с ботом — перешли её, куда захочешь")).toBeInTheDocument();
  });

  it("deletes the habit after a confirmation and goes back to the list", async () => {
    const view = show();
    const { calls } = mockApi({ "GET /me": me, "GET /habits/7": DETAIL, "DELETE /habits/7": { status: 204 } });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить привычку" }));
    await waitFor(() => expect(view.history.at(-1)).toBe("/habits"));
    await waitFor(() => expect(calls).toContainEqual({ method: "DELETE", path: "/habits/7", body: undefined }));
  });

  it("keeps the habit when the deletion is not confirmed", async () => {
    const app = installTelegram({
      showConfirm: vi.fn((_m: string, callback: (ok: boolean) => void) => callback(false)),
    });
    const view = show();
    const { calls } = mockApi({ "GET /me": me, "GET /habits/7": DETAIL, "DELETE /habits/7": { status: 204 } });
    fireEvent.click(await screen.findByRole("button", { name: "Удалить привычку" }));
    await waitFor(() => expect(app.showConfirm).toHaveBeenCalled());
    // Time enough for a DELETE that should not be sent to go out and come back.
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
    expect(view.history.at(-1)).toBe("/habits/7");
    expect(screen.getByRole("heading", { level: 1, name: "Спорт" })).toBeInTheDocument();
  });

  it("links to its editor", async () => {
    show();
    expect(await screen.findByRole("link", { name: "Изменить" })).toHaveAttribute("href", "/habits/7/edit");
  });

  it("names the year of a first day that is not in this one", async () => {
    show({ ...DETAIL, created_on: "2025-06-02" });
    expect(await screen.findByText("Каждый день · с 2 июня 2025")).toBeInTheDocument();
  });

  it("says the habit is gone when it was deleted elsewhere", async () => {
    show({ status: 404, body: { status: 404, code: "not_found", title: "Not found" } });
    expect(await screen.findByText("Этой привычки уже нет.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "К привычкам" })).toHaveAttribute("href", "/habits");
  });

  it("keeps the habit on screen when a refresh fails, and still says so when it is deleted meanwhile", async () => {
    const { client } = show();
    expect(await screen.findByRole("heading", { level: 1, name: "Спорт" })).toBeInTheDocument();
    mockApi({ "GET /me": me, "GET /habits/7": RATE_LIMITED });
    await refresh(client, keys.habit(7));
    expect(screen.getByRole("heading", { level: 1, name: "Спорт" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    mockApi({ "GET /me": me, "GET /habits/7": { status: 404, body: { status: 404, code: "not_found", title: "Not found" } } });
    await refresh(client, keys.habit(7));
    expect(screen.getByText("Этой привычки уже нет.")).toBeInTheDocument();
  });

  it("speaks English", async () => {
    show(DETAIL, "en");
    expect(await screen.findByText("Every day · since September 14")).toBeInTheDocument();
    expect(screen.getByText("Streak")).toBeInTheDocument();
    expect(screen.getByText("5 days")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
  });
});
