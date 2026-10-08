import { Trash2 } from "lucide-react";
import { useRef, useState, type ReactNode, type TouchEvent } from "react";
import { confirmAction } from "../telegram";

const OPEN = -88;
/** A pointer that hovers — a mouse; app.css shows the delete button at rest under the same query. */
const WITH_MOUSE = "(hover: hover)";

/**
 * A row that reveals a delete button when swiped left. With a mouse the button is always on screen
 * and a click (or Tab and Enter) is the only step, so a row given a `question` asks it there first;
 * on a phone the swipe is that step. The button follows the row's content, so the keyboard and a
 * screen reader reach a row before its own delete.
 */
export function SwipeRow({
  onDelete, deleteLabel, question, children,
}: { onDelete: () => void; deleteLabel: string; question?: string; children: ReactNode }) {
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
  const remove = async () => {
    if (question !== undefined && window.matchMedia(WITH_MOUSE).matches && !(await confirmAction(question))) {
      return;
    }
    onDelete();
  };

  return (
    <div className="swipe" data-open={offset !== 0 ? "true" : "false"}>
      <div
        className="swipe__content"
        style={{ transform: `translateX(${offset}px)` }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {children}
      </div>
      <button type="button" className="swipe__delete" onClick={() => void remove()} aria-label={deleteLabel}>
        <Trash2 size={20} aria-hidden />
      </button>
    </div>
  );
}
