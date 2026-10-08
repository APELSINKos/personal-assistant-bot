import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { keys } from "../api/queries";
import type { Me } from "../api/types";
import { Toasts } from "../components/Toasts";
import { BOT_CHAT_URL } from "../lib/links";
import { installTelegram } from "../test/fakeTelegram";
import { me, scheduleSource } from "../test/fixtures";
import { mockApi, type ApiCall } from "../test/mockApi";
import { RATE_LIMITED, refresh } from "../test/refresh";
import { renderWithApp } from "../test/render";
import { ScheduleScreen } from "./Schedule";

const NOT_CALENDAR = {
  status: 422,
  body: { status: 422, code: "validation_error", title: "Invalid input", field: "calendar", reason: "not_calendar" },
};
const TWO_MIB = 2 * 1024 * 1024;

function show(lang: "ru" | "en" = "ru") {
  return renderWithApp(
    <>
      <ScheduleScreen />
      <Toasts />
    </>,
    { path: "/more/schedule", lang },
  );
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  return input;
}

/**
 * jsdom keeps no file selection of its own. This one behaves like a browser's: choosing the file
 * that is already chosen fires no `change`, and setting `value` to "" empties the choice.
 */
function browserFileInput(input: HTMLInputElement) {
  let chosen: File | undefined;
  Object.defineProperty(input, "files", { configurable: true, get: () => (chosen ? [chosen] : []) });
  Object.defineProperty(input, "value", {
    configurable: true,
    get: () => (chosen ? `C:\\fakepath\\${chosen.name}` : ""),
    set: (value: string) => {
      if (value === "") chosen = undefined;
    },
  });
  return {
    choose(file: File) {
      if (chosen === file) return;
      chosen = file;
      fireEvent.change(input);
    },
  };
}

/** A route that answers only when the test says so, so the screen can be seen in between. */
function held() {
  const waiting: ((reply: { status?: number; body?: unknown }) => void)[] = [];
  return {
    handler: () => new Promise<{ status?: number; body?: unknown }>((resolve) => waiting.push(resolve)),
    answer: (reply: { status?: number; body?: unknown }) => act(() => waiting.shift()?.(reply)),
  };
}

const searches = (calls: ApiCall[]) => calls.filter((call) => call.path.startsWith("/schedule/groups"));

describe("Schedule", () => {
  it("connects a MIREA group found by name", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=ikbo": { groups: [{ id: 4805, name: "ИКБО-63-24" }], building: false },
      "PUT /schedule": { source: scheduleSource },
    });
    show();
    expect(await screen.findByText(/Подключи расписание/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Группа МИРЭА"), { target: { value: "ikbo" } });
    fireEvent.click(await screen.findByRole("button", { name: "ИКБО-63-24" }));
    expect(await screen.findByText("Расписание подключено")).toBeInTheDocument();
    expect(calls).toContainEqual({ method: "PUT", path: "/schedule", body: { mirea_id: 4805 } });
    expect(screen.getByText("ИКБО-63-24")).toBeInTheDocument();
    expect(screen.getByText("Обновлено 28 сент., 15:00")).toBeInTheDocument();
    expect(screen.getByText("Впереди 36 пар")).toBeInTheDocument();
  });

  it("disables every group row while a group is being connected", async () => {
    installTelegram();
    const put = held();
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=ikbo": {
        groups: [{ id: 4805, name: "ИКБО-63-24" }, { id: 4804, name: "ИКБО-62-24" }],
        building: false,
      },
      "PUT /schedule": put.handler,
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "ikbo" } });
    fireEvent.click(await screen.findByRole("button", { name: "ИКБО-63-24" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "ИКБО-62-24" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "ИКБО-63-24" })).toBeDisabled();
    put.answer({ body: { source: scheduleSource } });
    expect(await screen.findByText("Расписание подключено")).toBeInTheDocument();
  });

  it("says when no group matches", async () => {
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=xyz": { groups: [], building: false },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "xyz" } });
    expect(await screen.findByText("Такой группы нет в справочнике")).toBeInTheDocument();
  });

  it("reads out what each group search found, in a region that was there before it", async () => {
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=ikbo": {
        groups: [{ id: 4804, name: "ИКБО-62-24" }, { id: 4805, name: "ИКБО-63-24" }],
        building: false,
      },
      "GET /schedule/groups?q=xyz": { groups: [], building: false },
    });
    show();
    const field = await screen.findByLabelText("Группа МИРЭА");
    // A screen reader reads out changes only in a region it already listens to.
    const regions = screen.getAllByRole("status");
    fireEvent.change(field, { target: { value: "ikbo" } });
    const region = (await screen.findByText("Найдено групп: 2")).closest('[role="status"]');
    expect(regions).toContain(region);
    fireEvent.change(field, { target: { value: "xyz" } });
    await waitFor(() => expect(region).toHaveTextContent("Такой группы нет в справочнике"));
    expect(region).not.toHaveTextContent("Найдено групп");
  });

  it("warns that the directory is still being built", async () => {
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=%D0%98%D0%9A%D0%91%D0%9E": {
        groups: [{ id: 4804, name: "ИКБО-62-24" }],
        building: true,
      },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "ИКБО" } });
    expect(await screen.findByRole("button", { name: "ИКБО-62-24" })).toBeInTheDocument();
    // Read out together with the count, like every notice of the search.
    expect(
      screen.getByText(
        "Справочник групп ещё не готов — если твоей группы нет, попробуй позже или подключи расписание по ссылке.",
      ).closest('[role="status"]'),
    ).toHaveTextContent("Найдено групп: 1");
    expect(screen.queryByText("Такой группы нет в справочнике")).not.toBeInTheDocument();
  });

  it("shows the generic text when the group search fails with a code the app has no text for", async () => {
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      // A code is a string from the server: it must not be looked up among what every object has.
      "GET /schedule/groups?q=ikbo": { status: 422, body: { status: 422, code: "__proto__", title: "Invalid input" } },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "ikbo" } });
    expect(await screen.findByText("Что-то пошло не так. Попробуй ещё раз.")).toBeInTheDocument();
    expect(screen.getByLabelText("Группа МИРЭА")).toBeInTheDocument();
  });

  it("says it is searching while the first answer is on the way, where the results are read out", async () => {
    installTelegram();
    const groups = held();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=ikbo": groups.handler,
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "ikbo" } });
    const searching = await screen.findByText("Ищу…");
    expect(searching.closest('[role="status"]')).toHaveAttribute("aria-live", "polite");
    // «Ищу…» is drawn as the search starts, a moment before its request goes out (an effect sends
    // it): the answer waits for the request, or it would answer nothing and the search would hang.
    await waitFor(() => expect(searches(calls)).toHaveLength(1));
    expect(screen.getByText("Ищу…")).toBeInTheDocument();
    groups.answer({ body: { groups: [{ id: 4805, name: "ИКБО-63-24" }], building: false } });
    expect(await screen.findByRole("button", { name: "ИКБО-63-24" })).toBeInTheDocument();
    expect(screen.queryByText("Ищу…")).not.toBeInTheDocument();
  });

  it("tries an unavailable group search once more, then says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=ikbo": { status: 503, body: { status: 503, code: "upstream_unavailable", title: "Unavailable" } },
    });
    show();
    fireEvent.change(await screen.findByLabelText("Группа МИРЭА"), { target: { value: "ikbo" } });
    expect(await screen.findByText("Ищу…")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(screen.getByText("Сервис временно недоступен")).toBeInTheDocument();
    expect(screen.queryByText("Ищу…")).not.toBeInTheDocument();
    expect(searches(calls)).toHaveLength(2);
  });

  it("starts looking for a group at two characters, and drops the suggestions below that", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups?q=%D0%B8%D0%BA": { groups: [{ id: 4805, name: "ИКБО-63-24" }], building: false },
    });
    show();
    const field = await screen.findByLabelText("Группа МИРЭА");
    fireEvent.change(field, { target: { value: "и" } });
    // Longer than the 300 ms the field waits for more typing: a search would have gone out by now.
    await act(() => new Promise((resolve) => setTimeout(resolve, 450)));
    expect(searches(calls)).toEqual([]);
    fireEvent.change(field, { target: { value: "ик" } });
    expect(await screen.findByRole("button", { name: "ИКБО-63-24" })).toBeInTheDocument();
    expect(searches(calls)).toHaveLength(1);
    // Cut back to one character, the suggestions go at once, not after the delay.
    fireEvent.change(field, { target: { value: "и" } });
    expect(screen.queryByRole("button", { name: "ИКБО-63-24" })).not.toBeInTheDocument();
  });

  it("counts a group search in characters as the server does, and sends none it would refuse", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "GET /schedule/groups": { groups: [{ id: 4805, name: "ИКБО-63-24" }], building: false },
    });
    show();
    const field = await screen.findByLabelText("Группа МИРЭА");
    fireEvent.change(field, { target: { value: "🎓" } }); // one character in two UTF-16 units
    await act(() => new Promise((resolve) => setTimeout(resolve, 450)));
    expect(searches(calls)).toEqual([]);

    fireEvent.change(field, { target: { value: "🎓".repeat(40) } });
    expect(await screen.findByRole("button", { name: "ИКБО-63-24" })).toBeInTheDocument();
    expect(searches(calls)).toHaveLength(1);

    fireEvent.change(field, { target: { value: "🎓".repeat(41) } });
    expect(screen.getByText("41/40")).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription("41/40");
    expect(screen.queryByRole("button", { name: "ИКБО-63-24" })).not.toBeInTheDocument();
    await act(() => new Promise((resolve) => setTimeout(resolve, 450)));
    expect(searches(calls)).toHaveLength(1);
  });

  it("counts a calendar link in characters, and sends none longer than the server takes", async () => {
    installTelegram();
    const { calls } = mockApi({ "GET /me": me, "GET /schedule": { source: null }, "PUT /schedule": NOT_CALENDAR });
    show();
    const field = await screen.findByLabelText("Ссылка на календарь");
    const connect = screen.getByRole("button", { name: "Подключить" });
    const link = `https://uni.example/${"📅".repeat(1980)}`; // 2000 characters, 3980 UTF-16 units
    fireEvent.change(field, { target: { value: `${link}📅` } });
    expect(screen.getByText("2001/2000")).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription("2001/2000");
    expect(connect).toBeDisabled();
    fireEvent.submit(field.closest("form") as HTMLFormElement); // Enter in the field

    fireEvent.change(field, { target: { value: link } });
    expect(connect).toBeEnabled();
    fireEvent.click(connect);
    expect(await screen.findByText("Это не похоже на календарь .ics")).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "PUT")).toEqual([{ method: "PUT", path: "/schedule", body: { url: link } }]);
  });

  it("explains why a link was refused and keeps the form", async () => {
    installTelegram();
    const { calls } = mockApi({ "GET /me": me, "GET /schedule": { source: null }, "PUT /schedule": NOT_CALENDAR });
    show();
    fireEvent.change(await screen.findByLabelText("Ссылка на календарь"), {
      target: { value: " https://uni.example/login " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Подключить" }));
    expect(await screen.findByText("Это не похоже на календарь .ics")).toBeInTheDocument();
    expect(calls).toContainEqual({ method: "PUT", path: "/schedule", body: { url: "https://uni.example/login" } });
    expect(screen.getByRole("button", { name: "Подключить" })).toBeInTheDocument();
  });

  it("keeps a link typed for another source when a refresh fails", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: scheduleSource } });
    const { client } = show();
    fireEvent.click(await screen.findByRole("button", { name: "Сменить источник" }));
    const link = "webcal://uni.example/timetable.ics";
    fireEvent.change(screen.getByLabelText("Ссылка на календарь"), { target: { value: link } });
    mockApi({ "GET /me": RATE_LIMITED, "GET /schedule": { source: scheduleSource } });
    await refresh(client, keys.me);
    expect(screen.getByLabelText("Ссылка на календарь")).toHaveValue(link);
    mockApi({ "GET /me": RATE_LIMITED, "GET /schedule": RATE_LIMITED });
    await refresh(client, keys.schedule);
    expect(screen.getByLabelText("Ссылка на календарь")).toHaveValue(link);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uploads a picked .ics file", async () => {
    installTelegram();
    const fileSource = { ...scheduleSource, kind: "file", title: "Английский", mirea_id: null, url: null };
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "POST /schedule/file": { source: fileSource },
    });
    show();
    await screen.findByRole("button", { name: "Выбрать файл" });
    const file = new File(["BEGIN:VCALENDAR"], "Английский.ics", { type: "text/calendar" });
    fireEvent.change(fileInput(), { target: { files: [file] } });
    expect(await screen.findByText("Расписание подключено")).toBeInTheDocument();
    expect(calls.find((call) => call.method === "POST")?.body).toBe(file);
    expect(screen.getByText("Файл .ics")).toBeInTheDocument();
    expect(screen.getByText(/Файл не обновляется сам/)).toBeInTheDocument();
    // A file has nothing new to download.
    expect(screen.queryByRole("button", { name: "Обновить" })).not.toBeInTheDocument();
  });

  it("refuses a file over 2 MB without sending it", async () => {
    installTelegram();
    const { calls } = mockApi({ "GET /me": me, "GET /schedule": { source: null } });
    show();
    await screen.findByRole("button", { name: "Выбрать файл" });
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.ics");
    fireEvent.change(fileInput(), { target: { files: [big] } });
    expect(await screen.findByText(/Календарь слишком большой/)).toBeInTheDocument();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("buzzes for a file over 2 MB the way it does for any other error", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: null } });
    show();
    await screen.findByRole("button", { name: "Выбрать файл" });
    fireEvent.change(fileInput(), { target: { files: [new File([new Uint8Array(TWO_MIB + 1)], "big.ics")] } });
    expect(await screen.findByText(/Календарь слишком большой/)).toBeInTheDocument();
    expect(app.HapticFeedback?.notificationOccurred).toHaveBeenCalledWith("error");
  });

  it("uploads a file of exactly 2 MB: the limit is inclusive", async () => {
    installTelegram();
    const fileSource = { ...scheduleSource, kind: "file", title: "exact", mirea_id: null, url: null };
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "POST /schedule/file": { source: fileSource },
    });
    show();
    await screen.findByRole("button", { name: "Выбрать файл" });
    const exact = new File([new Uint8Array(TWO_MIB)], "exact.ics");
    fireEvent.change(fileInput(), { target: { files: [exact] } });
    expect(await screen.findByText("Расписание подключено")).toBeInTheDocument();
    expect(calls.find((call) => call.method === "POST")?.body).toBe(exact);
    expect(screen.queryByText(/Календарь слишком большой/)).not.toBeInTheDocument();
  });

  it("lets the same file be chosen again after the server turned it down", async () => {
    installTelegram();
    const fileSource = { ...scheduleSource, kind: "file", title: "Английский", mirea_id: null, url: null };
    let uploads = 0;
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: null },
      "POST /schedule/file": () => {
        uploads += 1;
        return uploads === 1 ? NOT_CALENDAR : { body: { source: fileSource } };
      },
    });
    show();
    await screen.findByRole("button", { name: "Выбрать файл" });
    const picker = browserFileInput(fileInput());
    const file = new File(["BEGIN:VCALENDAR"], "Английский.ics", { type: "text/calendar" });
    picker.choose(file);
    expect(await screen.findByText("Это не похоже на календарь .ics")).toBeInTheDocument();
    picker.choose(file); // the file was fixed on disk, and the very same one is chosen again
    expect(await screen.findByText("Расписание подключено")).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(2);
  });

  it("refreshes, and reports a refresh that failed", async () => {
    installTelegram();
    let error: string | null = null;
    mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "POST /schedule/refresh": () => ({ body: { source: { ...scheduleSource, error } } }),
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Обновить" }));
    expect(await screen.findByText("Расписание обновлено")).toBeInTheDocument();
    error = "unreachable";
    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    expect(await screen.findByText(/Не получилось скачать календарь/)).toBeInTheDocument();
    expect(screen.getByText("Последнее обновление не удалось")).toBeInTheDocument();
  });

  it("keeps «Обновить» off and still reports the result when the card is drawn anew mid-refresh", async () => {
    installTelegram();
    const refresh = held();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "POST /schedule/refresh": refresh.handler,
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Обновить" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Обновить" })).toBeDisabled());
    // «Сменить источник» → «Отмена» while the refresh runs: a new card, not the one that started it.
    fireEvent.click(screen.getByRole("button", { name: "Сменить источник" }));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.getByRole("button", { name: "Обновить" })).toBeDisabled();
    refresh.answer({ body: { source: scheduleSource } });
    expect(await screen.findByText("Расписание обновлено")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Обновить" })).toBeEnabled());
    expect(calls.filter((call) => call.path === "/schedule/refresh")).toHaveLength(1);
  });

  it("marks old data when the source has been down for days", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: { ...scheduleSource, stale: true, error: "unreachable" } } });
    show();
    expect(await screen.findByText("⚠️ Данные от 28 сент., 15:00 — источник пока недоступен")).toBeInTheDocument();
    expect(screen.queryByText("Последнее обновление не удалось")).not.toBeInTheDocument();
  });

  it("disconnects after a confirmation", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "DELETE /schedule": { status: 204 },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Отключить" }));
    expect(app.showConfirm).toHaveBeenCalledWith(
      "Отключить расписание? Пары пропадут из календаря и «Моего дня».",
      expect.any(Function),
    );
    expect(await screen.findByText(/Подключи расписание/)).toBeInTheDocument();
    expect(calls).toContainEqual({ method: "DELETE", path: "/schedule", body: undefined });
  });

  it("keeps the source when the disconnect is not confirmed", async () => {
    const app = installTelegram({
      showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(false)),
    });
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "DELETE /schedule": { status: 204 },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Отключить" }));
    await waitFor(() => expect(app.showConfirm).toHaveBeenCalled());
    // Time enough for a DELETE that should not be sent to go out and come back.
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
    expect(screen.getByText("ИКБО-63-24")).toBeInTheDocument();
    expect(screen.queryByText(/Подключи расписание/)).not.toBeInTheDocument();
  });

  it("changes the source only when asked, and can go back", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: scheduleSource } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Сменить источник" }));
    expect(screen.getByLabelText("Группа МИРЭА")).toBeInTheDocument();
    expect(screen.queryByText(/Подключи расписание/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.getByText("ИКБО-63-24")).toBeInTheDocument();
  });

  it("returns to the source card once the new source is connected", async () => {
    installTelegram();
    const link = { ...scheduleSource, kind: "url", title: "uni.example", mirea_id: null, url: "https://uni.example/a.ics" };
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "PUT /schedule": { source: link },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Сменить источник" }));
    fireEvent.change(screen.getByLabelText("Ссылка на календарь"), { target: { value: "https://uni.example/a.ics" } });
    fireEvent.click(screen.getByRole("button", { name: "Подключить" }));
    expect(await screen.findByText("uni.example")).toBeInTheDocument();
    expect(calls).toContainEqual({ method: "PUT", path: "/schedule", body: { url: "https://uni.example/a.ics" } });
    // The source card, with its «Обновить», and not the connect form any more.
    expect(screen.getByRole("button", { name: "Обновить" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Группа МИРЭА")).not.toBeInTheDocument();
  });

  it("shows the pressed choice at once, before the save has answered", async () => {
    installTelegram();
    const patch = held();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "PATCH /schedule": patch.handler,
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "30 мин" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "30 мин" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "Выкл" })).toHaveAttribute("aria-pressed", "false");
    expect(calls).toContainEqual({ method: "PATCH", path: "/schedule", body: { lesson_reminder_minutes: 30 } });
    patch.answer({ body: { source: { ...scheduleSource, lesson_reminder_minutes: 30 } } });
    await waitFor(() => expect(screen.getByRole("button", { name: "30 мин" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "Выкл" })).toHaveAttribute("aria-pressed", "false");
  });

  it("saves a choice without asking when the bot may already write", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /schedule": { source: scheduleSource },
      "PATCH /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: 30 } },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "30 мин" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PATCH", path: "/schedule", body: { lesson_reminder_minutes: 30 } }),
    );
    expect(app.requestWriteAccess).not.toHaveBeenCalled();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("turns alerts off without asking for the permission to write", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": { ...me, can_write: false },
      "GET /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: 15 } },
      "PATCH /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: null } },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Выкл" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PATCH", path: "/schedule", body: { lesson_reminder_minutes: null } }),
    );
    expect(app.requestWriteAccess).not.toHaveBeenCalled();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    await waitFor(() => expect(screen.getByRole("button", { name: "Выкл" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("turns lesson alerts on after the permission to write", async () => {
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": { ...me, can_write: false },
      "GET /schedule": { source: scheduleSource },
      "POST /me/write-access": { ...me, can_write: true },
      "PATCH /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: 15 } },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "15 мин" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "15 мин" })).toHaveAttribute("aria-pressed", "true"));
    expect(app.requestWriteAccess).toHaveBeenCalled();
    const paths = calls.filter((call) => call.method !== "GET").map((call) => `${call.method} ${call.path}`);
    expect(paths).toEqual(["POST /me/write-access", "PATCH /schedule"]);
    expect(calls.at(-1)?.body).toEqual({ lesson_reminder_minutes: 15 });
    expect(screen.getByRole("button", { name: "Выкл" })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps alerts off when the permission is refused", async () => {
    installTelegram({ requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => callback?.(false)) });
    const { calls } = mockApi({ "GET /me": { ...me, can_write: false }, "GET /schedule": { source: scheduleSource } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "30 мин" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Без разрешения бот не сможет прислать напоминание.");
    expect(calls.some((call) => call.method === "PATCH")).toBe(false);
    expect(screen.getByRole("button", { name: "Выкл" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the refusal as its own card under the alerts, with the way to the bot's chat", async () => {
    const app = installTelegram({ requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => callback?.(false)) });
    mockApi({ "GET /me": { ...me, can_write: false }, "GET /schedule": { source: scheduleSource } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "30 мин" }));
    const refusal = await screen.findByRole("alert");
    expect(within(refusal).getByRole("heading", { name: "Разрешить боту писать?" })).toBeInTheDocument();
    expect(refusal).toHaveTextContent("Без разрешения бот не сможет прислать напоминание.");
    // A card of its own, right below the alerts card, not a block inside it.
    expect(screen.getByRole("group", { name: "Напоминать о парах" }).closest(".card")?.nextElementSibling).toBe(refusal);
    fireEvent.click(within(refusal).getByRole("button", { name: "Открыть чат с ботом" }));
    expect(app.openTelegramLink).toHaveBeenCalledWith(BOT_CHAT_URL);
  });

  it("drops the refusal once the permission is there and a choice is saved", async () => {
    const app = installTelegram({ requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => callback?.(false)) });
    let canWrite = false;
    const { calls } = mockApi({
      "GET /me": () => ({ body: { ...me, can_write: canWrite } }),
      "GET /schedule": { source: scheduleSource },
      "PATCH /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: 30 } },
    });
    const { client } = show();
    fireEvent.click(await screen.findByRole("button", { name: "30 мин" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // The user presses Start in the bot's chat and comes back: the profile says so now.
    canWrite = true;
    await act(() => client.invalidateQueries({ queryKey: keys.me }));
    await waitFor(() => expect(client.getQueryData<Me>(keys.me)?.can_write).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "30 мин" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "30 мин" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(app.requestWriteAccess).toHaveBeenCalledTimes(1);
    expect(calls).toContainEqual({ method: "PATCH", path: "/schedule", body: { lesson_reminder_minutes: 30 } });
  });

  it("does not open a second permission prompt while the first one is open", async () => {
    const answers: ((allowed: boolean) => void)[] = [];
    const app = installTelegram({
      requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => {
        if (callback) answers.push(callback);
      }),
    });
    const { calls } = mockApi({
      "GET /me": { ...me, can_write: false },
      "GET /schedule": { source: scheduleSource },
      "POST /me/write-access": { ...me, can_write: true },
      "PATCH /schedule": { source: { ...scheduleSource, lesson_reminder_minutes: 15 } },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "15 мин" }));
    await waitFor(() => expect(app.requestWriteAccess).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "30 мин" })); // the first prompt is still open
    await act(async () => undefined);
    expect(app.requestWriteAccess).toHaveBeenCalledTimes(1);
    act(() => answers[0]?.(true));
    await waitFor(() => expect(screen.getByRole("button", { name: "15 мин" })).toHaveAttribute("aria-pressed", "true"));
    expect(calls.filter((call) => call.method === "PATCH").map((call) => call.body)).toEqual([
      { lesson_reminder_minutes: 15 },
    ]);
  });

  it("speaks English", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: scheduleSource } });
    show("en");
    expect(await screen.findByText("MIREA group")).toBeInTheDocument();
    expect(screen.getByText("36 classes ahead")).toBeInTheDocument();
    expect(screen.getByText("Updated Sep 28, 15:00")).toBeInTheDocument();
  });
});
