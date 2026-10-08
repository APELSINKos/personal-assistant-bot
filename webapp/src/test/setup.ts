// React's act environment: Testing Library turns it on only from a global beforeAll, and Vitest has none here.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { clearToasts } from "../components/toastStore";
import { setCalendarDay } from "../lib/calendarDay";
import { setNotesQuery } from "../lib/notesSearch";
import { removeTelegram } from "./fakeTelegram";

// A busy machine may take longer than Testing Library's default second to draw a screen.
configure({ asyncUtilTimeout: 3000 });

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
  setCalendarDay(null);
  setNotesQuery("");
  window.history.replaceState(null, "", "/");
  document.documentElement.removeAttribute("data-theme");
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
