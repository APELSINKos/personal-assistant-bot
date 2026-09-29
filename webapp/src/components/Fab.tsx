import { Plus } from "lucide-react";
import { Link } from "wouter";

export function Fab({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="fab" aria-label={label}>
      <Plus size={26} aria-hidden />
    </Link>
  );
}
