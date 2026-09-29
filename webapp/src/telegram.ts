import { useEffect, useRef } from "react";

export interface TgUser {
  id: number;
  first_name?: string;
  language_code?: string;
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
  onEvent(event: "themeChanged", callback: () => void): void;
  offEvent(event: "themeChanged", callback: () => void): void;
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

export function haptic(kind: "tap" | "select" | "success" | "error"): void {
  const feedback = supports("6.1") ? webApp()?.HapticFeedback : undefined;
  if (!feedback) return;
  if (kind === "tap") feedback.impactOccurred("light");
  else if (kind === "select") feedback.selectionChanged();
  else feedback.notificationOccurred(kind);
}

export function confirmAction(message: string): Promise<boolean> {
  const app = webApp();
  if (app?.showConfirm && supports("6.2")) {
    return new Promise((resolve) => app.showConfirm?.(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}

export function openLink(url: string): void {
  const app = webApp();
  if (app?.openLink) app.openLink(url);
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
