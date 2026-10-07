import type { CSSProperties } from "react";
import { Link } from "wouter";
import { useHabits, useMe, useSetMark } from "../api/queries";
import type { Habit } from "../api/types";
import { Card } from "../components/Card";
import { Fab } from "../components/Fab";
import { HabitToggle, nextMark, WeekDots } from "../components/HabitBits";
import { Empty, ErrorState, Loader } from "../components/States";
import { useT } from "../i18n";
import { localTodayIso } from "../lib/format";

function Progress({ habit }: { habit: Habit }) {
  const t = useT();
  const streak = habit.streak > 0 ? `🔥 ${t.habits.streakIn(habit.streak, habit.streak_unit)} · ` : "";
  const progress =
    habit.streak_unit === "weeks"
      ? t.habits.week(habit.week_done, habit.week_goal)
      : t.habits.progress(habit.done_days, habit.total_days);
  return <span className="habit__meta">{streak + progress}</span>;
}

export function HabitsScreen() {
  const t = useT();
  const me = useMe();
  // "Today" is the city's today; until /me names the city's zone, a mark could hit another day.
  const zone = me.data?.city.timezone;
  const habits = useHabits();
  const setMark = useSetMark();

  if (habits.isPending) return <Loader />;
  // A failed refresh keeps the list on screen: only a first load that failed is an error.
  if (habits.isLoadingError) return <ErrorState onRetry={() => void habits.refetch()} />;
  // Without /me no mark could ever be made: «Повторить» asks for it again, where every toggle
  // would wait, disabled, for an answer that is not coming. A failed refresh keeps the zone known.
  if (me.isLoadingError) return <ErrorState onRetry={() => void me.refetch()} />;

  return (
    <>
      <h1 className="screen__title">{t.tabs.habits}</h1>
      {habits.data.length === 0 && <Empty text={t.habits.empty} />}
      {habits.data.map((habit, index) => (
        <Card key={habit.id} index={index}>
          <div className="habit" style={{ "--habit": `var(--habit-${habit.color})` } as CSSProperties}>
            <Link href={`/habits/${habit.id}`} className="habit__open">
              <span className="habit__emoji" aria-hidden>{habit.emoji}</span>
              <span className="habit__text">
                <span className="habit__name">{habit.name}</span>
                <Progress habit={habit} />
              </span>
            </Link>
            <HabitToggle
              habit={habit}
              disabled={zone === undefined}
              onToggle={() => {
                if (zone) setMark.mutate({ id: habit.id, day: localTodayIso(zone), done: nextMark(habit.done_today) });
              }}
            />
            <WeekDots week={habit.week} />
          </div>
        </Card>
      ))}
      <Fab href="/habits/new" label={t.habits.add} />
    </>
  );
}
