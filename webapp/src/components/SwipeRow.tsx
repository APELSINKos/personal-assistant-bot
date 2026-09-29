import { Trash2 } from "lucide-react";
import { useRef, useState, type ReactNode, type TouchEvent } from "react";

const OPEN = -88;

/** A row that reveals a delete button when swiped left (always visible with a mouse). */
export function SwipeRow({
  onDelete, deleteLabel, children,
}: { onDelete: () => void; deleteLabel: string; children: ReactNode }) {
  const start = useRef<{ x: number; y: number; base: number } | null>(null);
  const [offset, setOffset] = useState(0);

  const onTouchStart = (event: TouchEvent) => {
    const touch = event.touches[0];
    if (touch) start.current = { x: touch.clientX, y: touch.clientY, base: offset };
  };
  const onTouchMove = (event: TouchEvent) => {
    const touch = event.touches[0];
    if (!start.current || !touch) return;
    const dx = touch.clientX - start.current.x;
    const dy = touch.clientY - start.current.y;
    if (Math.abs(dx) > Math.abs(dy)) setOffset(Math.min(0, Math.max(OPEN, start.current.base + dx)));
  };
  const onTouchEnd = () => {
    start.current = null;
    setOffset((value) => (value < OPEN / 2 ? OPEN : 0));
  };

  return (
    <div className="swipe" data-open={offset !== 0 ? "true" : "false"}>
      <button type="button" className="swipe__delete" onClick={onDelete} aria-label={deleteLabel}>
        <Trash2 size={20} aria-hidden />
      </button>
      <div
        className="swipe__content"
        style={{ transform: `translateX(${offset}px)` }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {children}
      </div>
    </div>
  );
}
