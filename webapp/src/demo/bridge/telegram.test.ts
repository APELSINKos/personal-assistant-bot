import { describe, expect, it, vi } from "vitest";
import {
  colorScheme, confirmAction, haptic, onThemeChange, paintTelegram, requestWriteAccess, shareMessage, startTelegram,
  webApp, type TgWebApp,
} from "../../telegram";
import { installTelegram } from "./telegram";
import { testHost } from "./testHost";

/** The stand-in as the app finds it. */
function app(): TgWebApp {
  const found = webApp();
  if (!found) throw new Error("The app finds no Telegram");
  return found;
}

/** Lets the host's answers reach the app. */
async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("the Telegram bridge", () => {
  it("opens the app as Telegram would: the visitor, initData, version 8.0", () => {
    const { host } = testHost();
    installTelegram(host);
    expect(app().initDataUnsafe.user).toEqual({ id: 1, first_name: "Саша", language_code: "ru" });
    expect(app().initDataUnsafe.user).not.toBe(host.user);
    const data = new URLSearchParams(app().initData);
    expect(data.get("demo")).toBe("1");
    expect(JSON.parse(data.get("user") ?? "null")).toEqual(host.user);
    expect(app().version).toBe("8.0");
    expect(host.connect).toHaveBeenCalledOnce();
  });

  it("compares versions part by part, as numbers", () => {
    installTelegram(testHost().host);
    expect(app().isVersionAtLeast("6.1")).toBe(true);
    expect(app().isVersionAtLeast("7.10")).toBe(true);
    expect(app().isVersionAtLeast("8.0")).toBe(true);
    expect(app().isVersionAtLeast("8.1")).toBe(false);
    expect(app().isVersionAtLeast("10.0")).toBe(false);
  });

  it("tells the host the app is ready", () => {
    const { host } = testHost();
    installTelegram(host);
    startTelegram();
    expect(host.ready).toHaveBeenCalledOnce();
  });

  it("paints the host's header, background and bottom bar", () => {
    const { host } = testHost();
    installTelegram(host);
    paintTelegram("light");
    expect(host.paint.mock.calls).toEqual([["header", "#f7f5f2"], ["background", "#f7f5f2"], ["bottom", "#f7f5f2"]]);
  });

  it("reads the host's theme and passes its change on", () => {
    const stand = testHost();
    installTelegram(stand.host);
    expect(colorScheme()).toBe("dark");
    const changed = vi.fn();
    const stop = onThemeChange(changed);
    stand.host.scheme.mockReturnValue("light");
    stand.frame().themeChanged();
    expect(changed).toHaveBeenCalledOnce();
    expect(colorScheme()).toBe("light");
    stop();
    stand.frame().themeChanged();
    expect(changed).toHaveBeenCalledOnce();
  });

  it("hands the main button to the host and passes its press back", () => {
    const stand = testHost();
    installTelegram(stand.host);
    const button = app().MainButton;
    const pressed = vi.fn();
    button.onClick(pressed);
    button.setParams({ text: "Сохранить", is_active: true, is_visible: true });
    expect(stand.host.mainButton).toHaveBeenLastCalledWith(
      { text: "Сохранить", visible: true, active: true, progress: false },
    );
    stand.frame().mainButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
    button.offClick(pressed);
    button.hide();
    expect(stand.host.mainButton).toHaveBeenLastCalledWith(
      { text: "Сохранить", visible: false, active: true, progress: false },
    );
    stand.frame().mainButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("passes no press of an inactive main button on, as Telegram does", () => {
    const stand = testHost();
    installTelegram(stand.host);
    const button = app().MainButton;
    const pressed = vi.fn();
    button.onClick(pressed);
    button.setParams({ text: "Сохранить", is_active: false, is_visible: true });
    expect(stand.host.mainButton).toHaveBeenLastCalledWith(
      { text: "Сохранить", visible: true, active: false, progress: false },
    );
    stand.frame().mainButtonClicked();
    expect(pressed).not.toHaveBeenCalled();
    button.showProgress?.(true);
    stand.frame().mainButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("shows the main button's progress and, as Telegram does, makes it active when it ends", () => {
    const stand = testHost();
    installTelegram(stand.host);
    const button = app().MainButton;
    button.setParams({ text: "Сохранить", is_active: true, is_visible: true });
    button.showProgress?.(false);
    expect(stand.host.mainButton).toHaveBeenLastCalledWith(
      { text: "Сохранить", visible: true, active: false, progress: true },
    );
    button.setParams({ is_active: false });
    button.hideProgress?.();
    expect(stand.host.mainButton).toHaveBeenLastCalledWith(
      { text: "Сохранить", visible: true, active: true, progress: false },
    );
  });

  it("shows the back button in the host and passes its press back", () => {
    const stand = testHost();
    installTelegram(stand.host);
    const back = app().BackButton;
    const pressed = vi.fn();
    back.onClick(pressed);
    back.show();
    expect(stand.host.backButton).toHaveBeenLastCalledWith(true);
    stand.frame().backButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
    back.offClick(pressed);
    back.hide();
    expect(stand.host.backButton).toHaveBeenLastCalledWith(false);
    stand.frame().backButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("keeps each listener once however often it subscribes, as Telegram does", () => {
    const stand = testHost();
    installTelegram(stand.host);
    const pressed = vi.fn();
    app().BackButton.onClick(pressed);
    app().BackButton.onClick(pressed);
    stand.frame().backButtonClicked();
    expect(pressed).toHaveBeenCalledOnce();
  });

  it("asks the host to confirm", async () => {
    const stand = testHost();
    stand.host.confirm.mockResolvedValueOnce(false);
    installTelegram(stand.host);
    await expect(confirmAction("Удалить заметку?")).resolves.toBe(false);
    await expect(confirmAction("Удалить заметку?")).resolves.toBe(true);
    expect(stand.host.confirm).toHaveBeenCalledWith("Удалить заметку?");
  });

  it("turns the closing confirmation on and off in the host", () => {
    const stand = testHost();
    installTelegram(stand.host);
    app().enableClosingConfirmation?.();
    app().disableClosingConfirmation?.();
    expect(stand.host.closingConfirmation.mock.calls).toEqual([[true], [false]]);
  });

  it("shares a prepared message through the host's chat picker", async () => {
    const stand = testHost();
    installTelegram(stand.host);
    await expect(shareMessage("demo-7-1")).resolves.toBe("sent");
    expect(stand.host.share).toHaveBeenCalledWith("demo-7-1");
  });

  it("answers a cancelled picker with false, then shareMessageFailed in the same turn", async () => {
    const stand = testHost();
    stand.host.share.mockResolvedValueOnce(false);
    installTelegram(stand.host);
    const order: string[] = [];
    app().onEvent("shareMessageFailed", (failure) => order.push(`event ${failure.error}`));
    app().shareMessage?.("demo-7-1", (sent) => {
      order.push(`callback ${sent}`);
      queueMicrotask(() => order.push("next turn"));
    });
    await settle();
    expect(order).toEqual(["callback false", "event USER_DECLINED", "next turn"]);
  });

  it("lets the app see a cancelled picker as declined", async () => {
    const stand = testHost();
    stand.host.share.mockResolvedValueOnce(false);
    installTelegram(stand.host);
    await expect(shareMessage("demo-7-1")).resolves.toBe("declined");
  });

  it("refuses a second picker while one is open, as Telegram does", async () => {
    const stand = testHost();
    let close: (sent: boolean) => void = () => undefined;
    stand.host.share.mockImplementationOnce(() => new Promise((resolve) => {
      close = resolve;
    }));
    installTelegram(stand.host);
    const first = shareMessage("demo-7-1");
    await expect(shareMessage("demo-7-2")).resolves.toBe("declined");
    close(true);
    await expect(first).resolves.toBe("sent");
    expect(stand.host.share).toHaveBeenCalledOnce();
  });

  it("asks the host for write access", async () => {
    const stand = testHost();
    stand.host.writeAccess.mockResolvedValueOnce(false);
    installTelegram(stand.host);
    await expect(requestWriteAccess()).resolves.toBe(false);
    await expect(requestWriteAccess()).resolves.toBe(true);
  });

  it("opens links in a new tab, the bot's chat too", () => {
    installTelegram(testHost().host);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    app().openLink?.("https://open-meteo.com/");
    app().openTelegramLink?.("https://t.me/ikbo63_24_bot");
    expect(open.mock.calls).toEqual([
      ["https://open-meteo.com/", "_blank", "noopener"],
      ["https://t.me/ikbo63_24_bot", "_blank", "noopener"],
    ]);
  });

  it("vibrates where the browser can, and stays silent elsewhere", () => {
    installTelegram(testHost().host);
    expect(() => haptic("tap")).not.toThrow();
    const vibrate = vi.fn(() => true);
    Object.defineProperty(navigator, "vibrate", { value: vibrate, configurable: true });
    try {
      haptic("tap");
      haptic("select");
      haptic("success");
      expect(vibrate).toHaveBeenCalledTimes(3);
    } finally {
      Reflect.deleteProperty(navigator, "vibrate");
    }
  });
});
