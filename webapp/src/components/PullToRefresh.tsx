import { useRef, useState, type ReactNode, type TouchEvent } from "react";
import { useT } from "../i18n";
import { haptic } from "../telegram";

const TRIGGER = 64;
const MAX_PULL = 88;

export function PullToRefresh({ onRefresh, children }: { onRefresh: () => Promise<unknown>; children: ReactNode }) {
  const t = useT();
  const start = useRef<number | null>(null);
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);

  const onTouchStart = (event: TouchEvent) => {
    start.current = window.scrollY <= 0 && !busy ? (event.touches[0]?.clientY ?? null) : null;
  };
  const onTouchMove = (event: TouchEvent) => {
    if (start.current === null) return;
    const distance = (event.touches[0]?.clientY ?? start.current) - start.current;
    setPull(distance > 0 ? Math.min(distance * 0.5, MAX_PULL) : 0);
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
