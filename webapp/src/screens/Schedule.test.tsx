import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { me, scheduleSource } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { ScheduleScreen } from "./Schedule";

const NOT_CALENDAR = {
  status: 422,
  body: { status: 422, code: "validation_error", title: "Invalid input", field: "calendar", reason: "not_calendar" },
};

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
    expect(screen.getByText(/Справочник групп ещё собирается/)).toBeInTheDocument();
    expect(screen.queryByText("Такой группы нет в справочнике")).not.toBeInTheDocument();
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

  it("speaks English", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /schedule": { source: scheduleSource } });
    show("en");
    expect(await screen.findByText("MIREA group")).toBeInTheDocument();
    expect(screen.getByText("36 classes ahead")).toBeInTheDocument();
    expect(screen.getByText("Updated Sep 28, 15:00")).toBeInTheDocument();
  });
});
