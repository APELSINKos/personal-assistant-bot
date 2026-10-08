import { Check, Circle, X } from "lucide-react";
import { Link } from "wouter";
import { ApiError } from "../api/client";
import type { Habit } from "../api/types";
import { useT } from "../i18n";
import { dayState } from "../lib/habits";
import { ErrorState } from "./States";

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

const WEEK_DOT = { done: "dot dot--done", missed: "dot dot--skipped", none: "dot", outside: "dot dot--ahead" };

/** This week, Monday to Sunday; days ahead (and before the habit began) are hollow. */
export function WeekDots({ week }: { week: string }) {
  return (
    <div className="dots" aria-hidden>
      {Array.from(week).map((char, index) => (
        <i key={index} className={WEEK_DOT[dayState(char)]} />
      ))}
    </div>
  );
}

export function HabitToggle({ habit, onToggle }: { habit: Habit; onToggle: () => void }) {
  const t = useT();
  const state = habit.done_today === true ? "done" : habit.done_today === false ? "skipped" : "none";
  const Icon = state === "done" ? Check : state === "skipped" ? X : Circle;
  return (
    <button
      type="button"
      className={`toggle toggle--${state}`}
      onClick={onToggle}
      aria-label={t.habits.toggle(habit.name, t.habits.state[state])}
    >
      <Icon size={20} aria-hidden />
    </button>
  );
}

/** A habit that could not be loaded: gone (404) with the way back to the list, or a retryable error. */
export function HabitLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useT();
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="empty">
        <p>{t.habits.gone}</p>
        <Link href="/habits" className="button">{t.habits.toHabits}</Link>
      </div>
    );
  }
  return <ErrorState onRetry={onRetry} />;
}
