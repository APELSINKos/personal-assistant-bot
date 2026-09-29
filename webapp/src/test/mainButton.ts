import { act } from "react";
import { vi } from "vitest";
import type { TgWebApp } from "../telegram";

/** Press Telegram's bottom main button: call the handler the screen registered last. */
export function pressMainButton(app: TgWebApp): void {
  const calls = vi.mocked(app.MainButton.onClick).mock.calls;
  const handler = calls[calls.length - 1]?.[0];
  act(() => handler?.());
}
