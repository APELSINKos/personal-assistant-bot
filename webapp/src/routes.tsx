import type { ComponentType } from "react";

export interface AppRoute {
  path: string;
  component: ComponentType;
  /**
   * Telegram's back button appears on this screen and leads to `parent`.
   * Leave unset for a screen that handles the back button itself (e.g. to confirm discarding
   * unsaved edits before leaving) — setting `parent` here would make it navigate away directly,
   * bypassing that screen's own confirmation.
   */
  parent?: string;
  /** Full-screen forms hide the bottom navigation. */
  hideNav?: boolean;
}

/** Screens register themselves here (Tasks 8–10); the first matching path wins. */
export const ROUTES: AppRoute[] = [];
