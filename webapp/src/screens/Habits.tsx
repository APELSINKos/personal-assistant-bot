import { Trash2 } from "lucide-react";
import { useDeleteHabit, useHabits, useSetMark } from "../api/queries";
import type { Habit } from "../api/types";
import { Card } from "../components/Card";
import { Fab } from "../components/Fab";
import { HabitDots, HabitToggle, nextMark } from "../components/HabitBits";
import { Empty, ErrorState, Loader } from "../components/States";
import { useT } from "../i18n";
import { localTodayIso } from "../lib/format";
import { useCityZone } from "../lib/zone";
import { confirmAction } from "../telegram";

export function HabitsScreen() {
  const t = useT();
  const zone = useCityZone();
  const habits = useHabits();
  const setMark = useSetMark();
  const remove = useDeleteHabit();

  if (habits.isPending) return <Loader />;
  if (habits.isError) return <ErrorState onRetry={() => void habits.refetch()} />;

  const onDelete = async (habit: Habit) => {
    if (await confirmAction(t.habits.confirmDelete(habit.name))) remove.mutate(habit.id);
  };

  return (
    <>
      <h1 className="screen__title">{t.tabs.habits}</h1>
      {habits.data.length === 0 && <Empty text={t.habits.empty} />}
      {habits.data.map((habit, index) => (
        <Card key={habit.id} index={index}>
          <div className="habit">
            <div>
              <div className="habit__name">{habit.name}</div>
              <div className="habit__meta">
                {habit.streak > 0 && <span className="accent">🔥 {t.habits.streak(habit.streak)} · </span>}
                {t.habits.progress(habit.done_days, habit.total_days)}
              </div>
            </div>
            <div className="row">
              <HabitToggle
                habit={habit}
                onToggle={() =>
                  setMark.mutate({ id: habit.id, day: localTodayIso(zone), done: nextMark(habit.done_today) })
                }
              />
              <button
                type="button"
                className="icon-button"
                aria-label={t.habits.delete(habit.name)}
                onClick={() => void onDelete(habit)}
              >
                <Trash2 size={18} aria-hidden />
              </button>
            </div>
            <HabitDots days={habit.last_days} />
          </div>
        </Card>
      ))}
      <Fab href="/habits/new" label={t.habits.add} />
    </>
  );
}
