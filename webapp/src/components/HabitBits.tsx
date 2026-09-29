import { Check, Circle, X } from "lucide-react";
import type { Habit } from "../api/types";
import { useT } from "../i18n";

export function nextMark(done: boolean | null): boolean | null {
  if (done === null) return true;
  return done ? false : null;
}

export function HabitDots({ days }: { days: (boolean | null)[] }) {
  return (
    <div className="dots" aria-hidden>
      {days.map((day, index) => (
        <i key={index} className={day === true ? "dot dot--done" : day === false ? "dot dot--skipped" : "dot"} />
      ))}
    </div>
  );
}

export function HabitToggle(
  { habit, onToggle, disabled = false }: { habit: Habit; onToggle: () => void; disabled?: boolean },
) {
  const t = useT();
  const state = habit.done_today === true ? "done" : habit.done_today === false ? "skipped" : "none";
  const Icon = state === "done" ? Check : state === "skipped" ? X : Circle;
  return (
    <button
      type="button"
      className={`toggle toggle--${state}`}
      disabled={disabled}
      onClick={onToggle}
      aria-label={t.habits.toggle(habit.name, t.habits.state[state])}
    >
      <Icon size={20} aria-hidden />
    </button>
  );
}
