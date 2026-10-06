import { Plus } from "lucide-react";
import { Link } from "wouter";

/**
 * The floating add button; it comes after a screen's list and keeps room after it, so the button
 * never covers the list's last row. With `onBlocked` (a limit is reached) it stays in its place,
 * dimmed, and a tap calls `onBlocked` — to say why — instead of opening the form.
 */
export function Fab({ href, label, onBlocked }: { href: string; label: string; onBlocked?: () => void }) {
  return (
    <>
      <div className="fab-room" aria-hidden="true" />
      <Link
        href={href}
        className="fab"
        aria-label={label}
        aria-disabled={onBlocked ? "true" : undefined}
        onClick={(event) => {
          if (!onBlocked) return;
          event.preventDefault();
          onBlocked();
        }}
      >
        <Plus size={26} aria-hidden />
      </Link>
    </>
  );
}
