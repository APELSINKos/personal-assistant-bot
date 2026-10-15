import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MainAction } from "../../components/MainAction";
import { confirmAction, requestWriteAccess, shareMessage, useBackButton } from "../../telegram";
import type { DemoHost } from "../bridge/contract";
import { installTelegram } from "../bridge/telegram";
import { createDevice } from "./device";
import { WORDS } from "./words";

/** The app's own code with the frame's bridge to a device: here both live in one window. */
function standWithApp() {
  const device = createDevice({ language: () => "ru", words: () => WORDS.ru });
  document.body.append(device.element);
  device.open("/");
  const host: DemoHost = {
    language: "ru",
    user: { id: 1, first_name: "Саша", language_code: "ru" },
    clockOffset: null,
    scheme: () => "dark",
    api: () => ({ status: 404, body: null, headers: {} }),
    ...device.chrome,
  };
  installTelegram(host);
  return device;
}

function BackTo({ onBack }: { onBack: () => void }) {
  useBackButton(onBack);
  return null;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("Telegram's chrome in the demo, as the app uses it", () => {
  it("shows the main button of a form that cannot be saved as inactive, and a press does nothing", () => {
    standWithApp();
    const save = vi.fn();
    const { rerender } = render(<MainAction text="Сохранить" onClick={save} disabled />);
    const button = screen.getByRole("button", { name: "Сохранить" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    button.click();
    expect(save).not.toHaveBeenCalled();

    rerender(<MainAction text="Сохранить" onClick={save} busy />);
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");

    rerender(<MainAction text="Сохранить" onClick={save} />);
    expect(button).toHaveAttribute("aria-disabled", "false");
    button.click();
    expect(save).toHaveBeenCalledOnce();
  });

  it("goes back with the header's «‹ Назад»", () => {
    standWithApp();
    const back = vi.fn();
    const { unmount } = render(<BackTo onBack={back} />);
    screen.getByRole("button", { name: "Назад" }).click();
    expect(back).toHaveBeenCalledOnce();
    unmount();
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeInTheDocument();
  });

  it("answers the app's question from the dialog", async () => {
    standWithApp();
    const answer = confirmAction("Удалить заметку?");
    within(screen.getByRole("dialog", { name: "Удалить заметку?" })).getByRole("button", { name: "OK" }).click();
    await expect(answer).resolves.toBe(true);
  });

  it("lets the app see a sent and a cancelled chat picker as Telegram reports them", async () => {
    standWithApp();
    const sent = shareMessage("demo-habit-1-1");
    within(screen.getByRole("dialog")).getByRole("button", { name: "Отправить" }).click();
    await expect(sent).resolves.toBe("sent");
    const cancelled = shareMessage("demo-forecast-0-1");
    within(screen.getByRole("dialog")).getByRole("button", { name: "Отмена" }).click();
    await expect(cancelled).resolves.toBe("declined");
  });

  it("asks for the bot's permission when the app wants it", async () => {
    standWithApp();
    const allowed = requestWriteAccess();
    within(screen.getByRole("dialog")).getByRole("button", { name: "Разрешить" }).click();
    await expect(allowed).resolves.toBe(true);
  });
});
