import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "./test/fakeTelegram";
import {
  confirmAction, haptic, initData, paintTelegram, startTelegram, webApp,
} from "./telegram";

describe("telegram", () => {
  it("is absent outside Telegram and with empty initData", () => {
    expect(webApp()).toBeNull();
    installTelegram({ initData: "" });
    expect(webApp()).toBeNull();
    expect(initData()).toBeNull();
  });

  it("starts, paints and gives haptics inside Telegram", () => {
    const app = installTelegram();
    expect(initData()).toContain("hash=abc");
    startTelegram();
    expect(app.ready).toHaveBeenCalled();
    expect(app.expand).toHaveBeenCalled();
    expect(app.disableVerticalSwipes).toHaveBeenCalled();
    paintTelegram("dark");
    expect(app.setHeaderColor).toHaveBeenCalledWith("#0a0913");
    expect(app.setBottomBarColor).toHaveBeenCalledWith("#0a0913");
    haptic("tap");
    expect(app.HapticFeedback?.impactOccurred).toHaveBeenCalledWith("light");
  });

  it("skips features the Telegram client is too old for", () => {
    const app = installTelegram({}, "6.0");
    startTelegram();
    expect(app.disableVerticalSwipes).not.toHaveBeenCalled();
    paintTelegram("light");
    expect(app.setHeaderColor).not.toHaveBeenCalled();
  });

  it("confirms through Telegram, or the browser outside it", async () => {
    const app = installTelegram();
    await expect(confirmAction("Удалить?")).resolves.toBe(true);
    expect(app.showConfirm).toHaveBeenCalled();
    window.Telegram = undefined;
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await expect(confirmAction("Удалить?")).resolves.toBe(false);
  });
});
