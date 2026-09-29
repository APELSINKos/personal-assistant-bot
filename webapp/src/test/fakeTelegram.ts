import { vi } from "vitest";
import type { TgWebApp } from "../telegram";

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
    onEvent: vi.fn(),
    offEvent: vi.fn(),
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

export function removeTelegram(): void {
  delete window.Telegram;
}
