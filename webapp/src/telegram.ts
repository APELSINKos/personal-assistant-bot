import { useEffect, useRef } from "react";

export interface TgUser {
  id: number;
  first_name?: string;
  language_code?: string;
  allows_write_to_pm?: boolean;
}

interface TgButton {
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

interface TgMainButton extends TgButton {
  setParams(params: { text?: string; is_active?: boolean; is_visible?: boolean }): void;
  showProgress?(leaveActive?: boolean): void;
  hideProgress?(): void;
}

/** Why a prepared message did not go, in Telegram's words (Bot API 8.0): USER_DECLINED and so on. */
interface ShareFailure {
  error?: string;
}

/** The events the app listens to, each with what telegram-web-app.js passes its listeners. */
interface TgEvents {
  themeChanged: () => void;
  shareMessageFailed: (failure: ShareFailure) => void;
}

export interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: TgUser };
  version: string;
  colorScheme: "light" | "dark";
  isVersionAtLeast(version: string): boolean;
  ready(): void;
  expand(): void;
  disableVerticalSwipes?(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  setBottomBarColor?(color: string): void;
  enableClosingConfirmation?(): void;
  disableClosingConfirmation?(): void;
  showConfirm?(message: string, callback: (ok: boolean) => void): void;
  openLink?(url: string): void;
  requestWriteAccess?(callback?: (allowed: boolean) => void): void;
  shareMessage?(msgId: string, callback?: (sent: boolean) => void): void;
  openTelegramLink?(url: string): void;
  onEvent<E extends keyof TgEvents>(event: E, callback: TgEvents[E]): void;
  offEvent<E extends keyof TgEvents>(event: E, callback: TgEvents[E]): void;
  BackButton: TgButton;
  MainButton: TgMainButton;
  HapticFeedback?: {
    impactOccurred(style: "light" | "medium"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export const THEME_BACKGROUND = { dark: "#0a0913", light: "#f7f5f2" } as const;

const DEV_INIT_DATA = import.meta.env.DEV ? import.meta.env.VITE_DEV_INIT_DATA : undefined;

/** The Mini App object — only when the page really runs inside Telegram. */
export function webApp(): TgWebApp | null {
  const app = window.Telegram?.WebApp;
  return app && app.initData ? app : null;
}

function supports(version: string): boolean {
  return webApp()?.isVersionAtLeast(version) ?? false;
}

export function isDevSession(): boolean {
  return !webApp() && Boolean(DEV_INIT_DATA);
}

export function initData(): string | null {
  return webApp()?.initData ?? DEV_INIT_DATA ?? null;
}

export function telegramLanguage(): string | undefined {
  return webApp()?.initDataUnsafe.user?.language_code;
}

/**
 * Telegram's launch parameters live in the hash (`#tgWebAppData=…&tgWebAppVersion=…`);
 * telegram-web-app.js has already read them by the time this runs, so the hash can become
 * the app's route instead of leaving wouter's hash router with nothing to match.
 */
export function normalizeLaunchHash(): void {
  if (!window.location.hash.startsWith("#/")) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search + "#/");
  }
}

export function colorScheme(): "light" | "dark" {
  const app = webApp();
  if (app) return app.colorScheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function startTelegram(): void {
  const app = webApp();
  if (!app) return;
  app.ready();
  app.expand();
  if (supports("7.7")) app.disableVerticalSwipes?.();
}

/** telegram-web-app.js throws on a colour it does not take; a colour is never worth the app. */
function tryPaint(paint: () => void): void {
  try {
    paint();
  } catch {
    // Telegram keeps its own colour for that part.
  }
}

export function paintTelegram(scheme: "light" | "dark"): void {
  const app = webApp();
  if (!app || !supports("6.1")) return;
  const color = THEME_BACKGROUND[scheme];
  // The header takes a hex colour from 6.9 on, before that only a theme key; the background
  // takes one from 6.1, the bottom bar exists from 7.10.
  tryPaint(() => app.setHeaderColor?.(supports("6.9") ? color : "bg_color"));
  tryPaint(() => app.setBackgroundColor?.(color));
  if (supports("7.10")) tryPaint(() => app.setBottomBarColor?.(color));
}

export function onThemeChange(callback: () => void): () => void {
  const app = webApp();
  if (app) {
    app.onEvent("themeChanged", callback);
    return () => app.offEvent("themeChanged", callback);
  }
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

export function haptic(kind: "tap" | "select" | "success" | "warning" | "error"): void {
  const feedback = supports("6.1") ? webApp()?.HapticFeedback : undefined;
  if (!feedback) return;
  if (kind === "tap") feedback.impactOccurred("light");
  else if (kind === "select") feedback.selectionChanged();
  else feedback.notificationOccurred(kind);
}

export function confirmAction(message: string): Promise<boolean> {
  const app = webApp();
  if (app?.showConfirm && supports("6.2")) {
    return new Promise((resolve) => {
      try {
        app.showConfirm?.(message, resolve);
      } catch {
        // Telegram refuses a popup while another one is open, or a message too long: not a yes.
        resolve(false);
      }
    });
  }
  return Promise.resolve(window.confirm(message));
}

export function openLink(url: string): void {
  const app = webApp();
  if (app?.openLink) app.openLink(url);
  else window.open(url, "_blank", "noopener");
}

/** Whether this Telegram can share a message the bot prepared (Bot API 8.0). */
export function canShareMessages(): boolean {
  return Boolean(webApp()?.shareMessage) && supports("8.0");
}

/**
 * How sharing a prepared message ended: sent to the chat the user picked; declined (the picker
 * closed, or one is open already); unsupported (this Telegram cannot share it after all); failed.
 */
export type ShareOutcome = "sent" | "declined" | "unsupported" | "failed";

/**
 * What a reason in shareMessageFailed means when it is not the user's no: USER_DECLINED, any other
 * reason or none at all is a closed picker, as it always was.
 */
const SHARE_FAILURES = new Map<string, ShareOutcome>([
  ["UNSUPPORTED", "unsupported"],
  ["MESSAGE_EXPIRED", "failed"],
  ["MESSAGE_SEND_FAILED", "failed"],
  ["UNKNOWN_ERROR", "failed"],
]);

/**
 * Opens Telegram's chat picker for a prepared message. Its callback says only whether the message
 * went; telegram-web-app.js gives the reason it did not in shareMessageFailed right after the
 * callback, in the same turn, so a «not sent» waits one turn for it.
 */
export function shareMessage(preparedId: string): Promise<ShareOutcome> {
  const app = webApp();
  if (!app?.shareMessage || !supports("8.0")) return Promise.resolve("unsupported");
  return new Promise((resolve) => {
    let reason: string | undefined;
    const failed = (failure: ShareFailure) => {
      reason = failure.error;
    };
    const end = (outcome: ShareOutcome) => {
      app.offEvent("shareMessageFailed", failed);
      resolve(outcome);
    };
    app.onEvent("shareMessageFailed", failed);
    try {
      app.shareMessage?.(preparedId, (sent) => {
        if (sent) end("sent");
        else setTimeout(() => end(SHARE_FAILURES.get(reason ?? "") ?? "declined"), 0);
      });
    } catch (error) {
      // A picker open already is the user's to finish; any other refusal is a Telegram that
      // cannot share after all.
      end(error instanceof Error && error.message === "WebAppShareMessageOpened" ? "declined" : "unsupported");
    }
  });
}

/** Telegram's own "Allow the bot to message you?" dialog; a soft `false` where unsupported. */
export function requestWriteAccess(): Promise<boolean> {
  const app = webApp();
  if (!app?.requestWriteAccess || !supports("6.9")) return Promise.resolve(false);
  return new Promise((resolve) => app.requestWriteAccess?.((allowed) => resolve(allowed)));
}

export function openTelegramLink(url: string): void {
  const app = webApp();
  if (app?.openTelegramLink && supports("6.1")) app.openTelegramLink(url);
  else window.open(url, "_blank", "noopener");
}

/** Shows Telegram's back button while `onBack` is set. */
export function useBackButton(onBack: (() => void) | null): void {
  const latest = useRef(onBack);
  useEffect(() => {
    latest.current = onBack;
  });
  const enabled = onBack !== null;
  useEffect(() => {
    const app = webApp();
    if (!app || !enabled || !supports("6.1")) return;
    const click = () => latest.current?.();
    app.BackButton.onClick(click);
    app.BackButton.show();
    return () => {
      app.BackButton.offClick(click);
      app.BackButton.hide();
    };
  }, [enabled]);
}

/** Asks Telegram to confirm closing the app while there are unsaved edits. */
export function useClosingConfirmation(enabled: boolean): void {
  useEffect(() => {
    const app = webApp();
    if (!app || !enabled || !supports("6.2")) return;
    app.enableClosingConfirmation?.();
    return () => app.disableClosingConfirmation?.();
  }, [enabled]);
}
