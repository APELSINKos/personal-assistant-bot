import { afterEach, describe, expect, it, vi } from "vitest";
import { installTelegram } from "./test/fakeTelegram";
import {
  confirmAction, haptic, initData, normalizeLaunchHash, paintTelegram, startTelegram, webApp,
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

  describe("normalizeLaunchHash", () => {
    afterEach(() => {
      window.history.replaceState(null, "", "/");
    });

    it("turns Telegram's launch parameters into the app's root route", () => {
      window.history.replaceState(null, "", "/#tgWebAppData=abc&tgWebAppVersion=8.0");
      normalizeLaunchHash();
      expect(window.location.hash).toBe("#/");
    });

    it("leaves an existing app route alone", () => {
      window.history.replaceState(null, "", "/#/habits");
      normalizeLaunchHash();
      expect(window.location.hash).toBe("#/habits");
    });

    it("turns a missing hash into the root route too", () => {
      window.history.replaceState(null, "", "/");
      normalizeLaunchHash();
      expect(window.location.hash).toBe("#/");
    });
  });
});
