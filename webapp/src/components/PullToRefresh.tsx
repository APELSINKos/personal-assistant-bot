import { useRef, useState, type ReactNode, type TouchEvent } from "react";
import { useT } from "../i18n";
import { haptic } from "../telegram";

const TRIGGER = 64;
const MAX_PULL = 88;
// How far the finger goes before its direction counts.
const DECIDE = 8;

interface Gesture {
  x: number;
  y: number;
  /** Up or down rather than sideways; null until the finger has gone DECIDE px. */
  vertical: boolean | null;
}

export function PullToRefresh({ onRefresh, children }: { onRefresh: () => Promise<unknown>; children: ReactNode }) {
  const t = useT();
  const start = useRef<Gesture | null>(null);
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);

  const onTouchStart = (event: TouchEvent) => {
    const touch = event.touches[0];
    start.current = window.scrollY <= 0 && !busy && touch ? { x: touch.clientX, y: touch.clientY, vertical: null } : null;
  };
  const onTouchMove = (event: TouchEvent) => {
    const gesture = start.current;
    const touch = event.touches[0];
    if (gesture === null || touch === undefined) return;
    const dx = touch.clientX - gesture.x;
    const dy = touch.clientY - gesture.y;
    if (gesture.vertical === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < DECIDE) return;
      // A sideways swipe scrolls the 24-hour strip or the city chips: it is no pull, however far
      // it drifts down afterwards.
      gesture.vertical = Math.abs(dy) > Math.abs(dx);
    }
    if (!gesture.vertical) return;
    setPull(dy > 0 ? Math.min(dy * 0.5, MAX_PULL) : 0);
  };
  const onTouchEnd = async () => {
    const shouldRefresh = pull >= TRIGGER;
    start.current = null;
    setPull(0);
    if (!shouldRefresh) return;
    haptic("tap");
    setBusy(true);
    try {
      await onRefresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
      <div className="ptr__indicator" aria-live="polite">
        {busy ? t.today.refreshing : pull > 0 ? t.today.pull : ""}
      </div>
      <div className="ptr__body" style={{ transform: `translateY(${pull}px)` }}>
        {children}
      </div>
    </div>
  );
}
