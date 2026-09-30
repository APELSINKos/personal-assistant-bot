import { afterEach, describe, expect, it, vi } from "vitest";
import { installTelegram, oldHeaderColor } from "./test/fakeTelegram";
import {
  confirmAction, haptic, initData, normalizeLaunchHash, paintTelegram,
  requestWriteAccess, startTelegram, webApp,
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

  it("gives clients before 6.9 the header colour key they accept", () => {
    const app = installTelegram({ setHeaderColor: oldHeaderColor() }, "6.5");
    paintTelegram("dark");
    expect(app.setHeaderColor).toHaveBeenCalledWith("bg_color");
    expect(app.setHeaderColor).not.toHaveBeenCalledWith("#0a0913");
    expect(app.setBackgroundColor).toHaveBeenCalledWith("#0a0913"); // a hex colour is fine from 6.1
    expect(app.setBottomBarColor).not.toHaveBeenCalled(); // 7.10 and later only
  });

  it("never lets a colour call take the app down", () => {
    const refuse = () => {
      throw new Error("WebAppBackgroundColorInvalid");
    };
    const app = installTelegram({ setHeaderColor: vi.fn(refuse), setBackgroundColor: vi.fn(refuse) });
    expect(() => paintTelegram("light")).not.toThrow();
    expect(app.setBottomBarColor).toHaveBeenCalledWith("#f7f5f2");
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

  describe("write access", () => {
    it("asks Telegram on 6.9+ and reports the answer", async () => {
      const app = installTelegram({
        requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => callback?.(true)),
      });
      await expect(requestWriteAccess()).resolves.toBe(true);
      expect(app.requestWriteAccess).toHaveBeenCalled();
    });

    it("is a soft no on older clients", async () => {
      const app = installTelegram({ requestWriteAccess: vi.fn() }, "6.5");
      await expect(requestWriteAccess()).resolves.toBe(false);
      expect(app.requestWriteAccess).not.toHaveBeenCalled();
    });
  });
});
