import { Plus } from "lucide-react";
import { Link } from "wouter";

/** The floating add button; it comes after a screen's list and keeps room after it, so the button
 *  never covers the list's last row. */
export function Fab({ href, label }: { href: string; label: string }) {
  return (
    <>
      <div className="fab-room" aria-hidden="true" />
      <Link href={href} className="fab" aria-label={label}>
        <Plus size={26} aria-hidden />
      </Link>
    </>
  );
}
