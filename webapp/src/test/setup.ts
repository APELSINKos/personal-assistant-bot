import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { clearToasts } from "../components/toastStore";
import { removeTelegram } from "./fakeTelegram";

if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

afterEach(() => {
  cleanup();
  removeTelegram();
  clearToasts();
  window.history.replaceState(null, "", "/");
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
