/** The app's frame and its host page: where the frame finds the host, and where it goes without one. */
import type { DemoHost, HostWindow } from "./contract";

/** The host page around this frame; null when app.html is a page of its own or framed by another site. */
export function parentHost(frame: Pick<Window, "parent"> = window): DemoHost | null {
  try {
    return (frame.parent as unknown as HostWindow).__demoHost ?? null;
  } catch {
    // A parent page of another origin refuses to be looked into.
    return null;
  }
}

/** The host page on the frame's screen: app.html#/weather opened by itself goes to ./#/weather. */
export function hostAddress(hash: string): string {
  return `./${hash.startsWith("#/") ? hash : "#/"}`;
}
