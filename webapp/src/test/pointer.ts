import { vi } from "vitest";

/**
 * Makes the screen's main pointer a mouse, which hovers (app.css's `(hover: hover)`), or a finger,
 * which does not. The setup puts the usual `matchMedia` back after each test.
 */
export function stubPointer(kind: "mouse" | "touch"): void {
  vi.stubGlobal("matchMedia", (query: string) =>
    ({
      matches: kind === "mouse" && query === "(hover: hover)",
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList);
}
