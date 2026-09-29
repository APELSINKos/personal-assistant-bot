import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { me, reminder } from "../test/fixtures";
import { pressMainButton } from "../test/mainButton";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { ReminderForm } from "./ReminderForm";
import { RemindersScreen } from "./Reminders";

function reminderAt(id: number, dueLocal: string, text: string) {
  return { ...reminder, id, text, due_local: dueLocal };
}

describe("Reminders", () => {
  it("groups upcoming reminders by day", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T12:00:00Z"));
    installTelegram();
    mockApi({
      "GET /me": me,
      "GET /reminders": [
        reminderAt(2, "2026-09-29T09:00", "Врач"),
        reminderAt(1, "2026-09-28T19:30", "Созвон"),
        reminderAt(3, "2026-10-02T08:00", "Отчёт"),
      ],
    });
    renderWithApp(<RemindersScreen />);
    const labels = await screen.findAllByRole("heading", { level: 2 });
    expect(labels.map((label) => label.textContent)).toEqual(["Сегодня", "Завтра", "Пт, 2 окт."]);
    expect(screen.getByText("Созвон")).toBeInTheDocument();
  });

  it("test_groups_use_the_city_day_not_the_device_day", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T20:00:00Z")); // already 29 September in Vladivostok
    installTelegram();
    mockApi({
      "GET /me": { ...me, city: { ...me.city, name: "Владивосток", timezone: "Asia/Vladivostok" } },
      "GET /reminders": [reminderAt(1, "2026-09-29T09:00", "Пробежка")],
    });
    renderWithApp(<RemindersScreen />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Сегодня"),
    );
  });

  it("deletes after confirmation", async () => {
    const app = installTelegram();
    // A handler (not a static list) for "GET /reminders": after the delete settles, the list
    // hook refetches to stay in sync with the server, and that refetch must see the row gone —
    // a fixed array would hand the stale row right back and undo the optimistic removal.
    let items = [reminder];
    const { calls } = mockApi({
      "GET /me": me,
      "GET /reminders": () => ({ body: items }),
      "DELETE /reminders/3": () => {
        items = [];
        return { status: 204 };
      },
    });
    renderWithApp(<RemindersScreen />);
    fireEvent.click(await screen.findByRole("button", { name: "Удалить напоминание" }));
    await waitFor(() => expect(screen.queryByText("Созвон")).not.toBeInTheDocument());
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить напоминание?", expect.any(Function));
    expect(calls).toContainEqual({ method: "DELETE", path: "/reminders/3", body: undefined });
  });

  it("shows the empty state", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /reminders": [] });
    renderWithApp(<RemindersScreen />);
    expect(await screen.findByText(/Напоминаний нет/)).toBeInTheDocument();
  });
});

describe("ReminderForm", () => {
  it("saves with Telegram's main button and returns to the list", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T12:10:00Z")); // 15:10 in Moscow
    const app = installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "POST /reminders": { status: 201, body: reminder },
    });
    const { history, client } = renderWithApp(<><ReminderForm /><Toasts /></>, {
      path: "/reminders/new",
    });
    await waitFor(() => expect(client.getQueryData(["me"])).toBeDefined()); // the city's zone
    await waitFor(() => expect(screen.getByLabelText("Время")).toHaveValue("16:00"));
    expect(screen.getByLabelText("Дата")).toHaveValue("2026-09-28");
    expect(app.MainButton.setParams).toHaveBeenLastCalledWith(expect.objectContaining({ is_active: false }));
    fireEvent.change(screen.getByLabelText("О чём напомнить"), { target: { value: "  Созвон  " } });
    fireEvent.change(screen.getByLabelText("Время"), { target: { value: "19:30" } });
    expect(app.MainButton.setParams).toHaveBeenLastCalledWith(expect.objectContaining({ is_active: true }));
    expect(app.enableClosingConfirmation).toHaveBeenCalled();
    pressMainButton(app);
    await waitFor(() => expect(history.at(-1)).toBe("/reminders"));
    expect(calls).toContainEqual({
      method: "POST", path: "/reminders", body: { text: "Созвон", due_local: "2026-09-28T19:30" },
    });
    expect(await screen.findByText("Напомню!")).toBeInTheDocument();
  });

  it("explains a moment in the past", async () => {
    const app = installTelegram();
    mockApi({
      "GET /me": me,
      "POST /reminders": {
        status: 422,
        body: { status: 422, code: "validation_error", title: "Invalid", field: "when", reason: "past" },
      },
    });
    renderWithApp(<><ReminderForm /><Toasts /></>, { path: "/reminders/new" });
    fireEvent.change(await screen.findByLabelText("О чём напомнить"), { target: { value: "x" } });
    pressMainButton(app);
    expect(await screen.findByText("Это время уже прошло")).toBeInTheDocument();
    expect(within(document.body).getByLabelText("О чём напомнить")).toHaveValue("x");
  });
});
