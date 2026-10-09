import { vi } from "vitest";
import type { TgWebApp } from "../telegram";

type Listener = (...args: unknown[]) => void;

/**
 * The installed app's listeners by event, the log telegram-web-app.js keeps of them: each listener
 * once however often it subscribes, in the order they came.
 */
let listeners = new Map<string, Listener[]>();

function compareVersions(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function button() {
  return { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() };
}

export function installTelegram(overrides: Partial<TgWebApp> = {}, version = "8.0"): TgWebApp {
  listeners = new Map();
  const app: TgWebApp = {
    initData: "query_id=q&user=%7B%22id%22%3A1%7D&auth_date=1&hash=abc",
    initDataUnsafe: { user: { id: 1, first_name: "Alex", language_code: "ru" } },
    version,
    colorScheme: "dark",
    isVersionAtLeast: (wanted: string) => compareVersions(version, wanted) >= 0,
    ready: vi.fn(),
    expand: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    setHeaderColor: vi.fn(),
    setBackgroundColor: vi.fn(),
    setBottomBarColor: vi.fn(),
    enableClosingConfirmation: vi.fn(),
    disableClosingConfirmation: vi.fn(),
    showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(true)),
    openLink: vi.fn(),
    requestWriteAccess: vi.fn((callback?: (allowed: boolean) => void) => callback?.(true)),
    shareMessage: vi.fn((_id: string, callback?: (sent: boolean) => void) => callback?.(true)),
    openTelegramLink: vi.fn(),
    onEvent: vi.fn((event: string, callback: Listener) => {
      const list = subscribers(event);
      if (!list.includes(callback)) listeners.set(event, [...list, callback]);
    }),
    offEvent: vi.fn((event: string, callback: Listener) => {
      listeners.set(event, subscribers(event).filter((listener) => listener !== callback));
    }),
    BackButton: button(),
    MainButton: { ...button(), setParams: vi.fn(), showProgress: vi.fn(), hideProgress: vi.fn() },
    HapticFeedback: {
      impactOccurred: vi.fn(),
      notificationOccurred: vi.fn(),
      selectionChanged: vi.fn(),
    },
    ...overrides,
  };
  window.Telegram = { WebApp: app };
  return app;
}

/** setHeaderColor as telegram-web-app.js has it before 6.9: a hex colour throws, only keys pass. */
export function oldHeaderColor() {
  return vi.fn((color: string) => {
    if (color !== "bg_color" && color !== "secondary_bg_color") {
      throw new Error("WebAppHeaderColorKeyInvalid");
    }
  });
}

/** The listeners the installed app holds for an event now. */
export function subscribers(event: string): readonly Listener[] {
  return listeners.get(event) ?? [];
}

/** Calls an event's listeners with its arguments, one after another, as telegram-web-app.js does. */
function emit(event: string, ...args: unknown[]): void {
  for (const listener of subscribers(event)) listener(...args);
}

/**
 * shareMessage as telegram-web-app.js answers a message that did not go: the callback with false,
 * then shareMessageFailed with Telegram's reason, in the same turn.
 */
export function shareFails(reason?: string) {
  return vi.fn((_id: string, callback?: (sent: boolean) => void) => {
    callback?.(false);
    emit("shareMessageFailed", { error: reason });
  });
}

export function removeTelegram(): void {
  delete window.Telegram;
  listeners = new Map();
}
