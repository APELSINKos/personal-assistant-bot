import type { ComponentType } from "react";

export interface AppRoute {
  path: string;
  component: ComponentType;
  /** Telegram's back button appears on this screen and leads to `parent`. */
  parent?: string;
  /** Full-screen forms hide the bottom navigation. */
  hideNav?: boolean;
}

/** Screens register themselves here (Tasks 8–10); the first matching path wins. */
export const ROUTES: AppRoute[] = [];
