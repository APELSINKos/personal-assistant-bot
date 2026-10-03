import type { ReactNode } from "react";
import { useLocation } from "wouter";
import { useBackButton } from "../telegram";

/**
 * Telegram's back button for a full-screen form that is still loading or could not load: the form
 * takes the button over once it shows, and the bottom navigation is hidden meanwhile.
 */
export function BackTo({ href, children }: { href: string; children: ReactNode }) {
  const [, navigate] = useLocation();
  useBackButton(() => navigate(href));
  return children;
}
