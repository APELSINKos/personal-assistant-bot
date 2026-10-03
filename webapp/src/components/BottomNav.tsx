import { CalendarDays, NotebookPen, Settings2, Sun, Target, Wallet } from "lucide-react";
import { Link, useLocation } from "wouter";
import { useT } from "../i18n";
import { haptic } from "../telegram";

const TABS = [
  { path: "/", key: "today", Icon: Sun },
  { path: "/calendar", key: "calendar", Icon: CalendarDays },
  { path: "/habits", key: "habits", Icon: Target },
  { path: "/notes", key: "notes", Icon: NotebookPen },
  { path: "/money", key: "money", Icon: Wallet },
  { path: "/more", key: "more", Icon: Settings2 },
] as const;

export function BottomNav() {
  const t = useT();
  const [location] = useLocation();
  return (
    <nav className="tabs" aria-label={t.common.sections}>
      {TABS.map(({ path, key, Icon }) => {
        const active = path === "/" ? location === "/" : location.startsWith(path);
        return (
          <Link
            key={path}
            href={path}
            className={active ? "tab tab--active" : "tab"}
            aria-current={active ? "page" : undefined}
            onClick={() => haptic("select")}
          >
            <Icon size={22} aria-hidden />
            <span>{t.tabs[key]}</span>
          </Link>
        );
      })}
    </nav>
  );
}
