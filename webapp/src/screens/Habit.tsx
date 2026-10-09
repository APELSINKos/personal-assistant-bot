import { ChevronLeft, ChevronRight } from "lucide-react";
import { type CSSProperties, useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import { isGone, useDeleteHabit, useHabit, useMarkDay, useMe, useShareHabit } from "../api/queries";
import type { HabitDetail } from "../api/types";
import { Card } from "../components/Card";
import { HabitLoadError } from "../components/HabitBits";
import { MonthMarks } from "../components/MonthMarks";
import { ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { WriteRefusedCard } from "../components/WriteRefusedCard";
import { YearMap } from "../components/YearMap";
import { useLang, useT } from "../i18n";
import { addDaysIso, dayMonth, localTodayIso, monthTitle } from "../lib/format";
import { DAILY, monthOfWeek, nextDone } from "../lib/habits";
import { useWriteAccess } from "../lib/useWriteAccess";
import { confirmAction } from "../telegram";

/** The first of the month `months` away from the month of `iso`. */
function shiftMonth(iso: string, months: number): string {
  const [year = 0, month = 1] = iso.split("-").map(Number);
  const index = year * 12 + month - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-01`;
}

/** The first day the habit can be marked on within its year map. */
function firstMarkable(habit: HabitDetail): string {
  const index = Math.max(habit.year.search(/[^.]/), 0);
  return addDaysIso(habit.year_from, index);
}

export function HabitScreen() {
  const t = useT();
  const lang = useLang();
  const [, navigate] = useLocation();
  const [, params] = useRoute<{ id: string }>("/habits/:id");
  const id = Number(params?.id);
  const habit = useHabit(id);
  const me = useMe();
  const zone = me.data?.city.timezone;
  const mark = useMarkDay();
  // Where Telegram cannot share from the app, the bot sends the card to its chat, once it may write.
  const write = useWriteAccess(me.data?.can_write);
  const share = useShareHabit(id, write.ensure);
  const remove = useDeleteHabit();
  const [month, setMonth] = useState<string | null>(null);

  // A failed refresh keeps the habit on screen: only a first load that failed is an error, and a
  // refresh that finds the habit deleted meanwhile says so.
  if (habit.isLoadingError || isGone(habit.error)) {
    return <HabitLoadError error={habit.error} onRetry={() => void habit.refetch()} />;
  }
  // The month is shown by the city's today: without /me there is none to wait for; a failed
  // refresh of /me keeps the zone already known.
  if (me.isLoadingError) return <ErrorState onRetry={() => void me.refetch()} />;
  if (habit.isPending || zone === undefined) return <Loader />;

  const data = habit.data;
  const today = localTodayIso(zone);
  const shown = month ?? `${today.slice(0, 7)}-01`;
  const first = firstMarkable(data);
  const goal = data.weekly_goal === DAILY ? t.habits.goalDaily : t.habits.goalWeekly(data.weekly_goal);
  // A habit begun last June must not seem to have begun this June.
  const since = dayMonth(data.created_on, lang, data.created_on.slice(0, 4) !== today.slice(0, 4));

  const onShare = () =>
    share.mutate(undefined, {
      onSuccess: (result) => {
        if (result === "sent") toast({ kind: "success", text: t.habits.cardSent });
      },
    });
  const onDelete = async () => {
    if (!(await confirmAction(t.habits.confirmDelete(data.name)))) return;
    remove.mutate(data.id);
    navigate("/habits");
  };

  return (
    <div className="habit-screen" style={{ "--habit": `var(--habit-${data.color})` } as CSSProperties}>
      <header className="habit-head">
        <span className="habit-head__emoji" aria-hidden>{data.emoji}</span>
        <div className="habit-head__text">
          <h1 className="screen__title habit-head__name">{data.name}</h1>
          <p className="muted">{`${goal} · ${t.habits.since(since)}`}</p>
        </div>
      </header>

      <div className="habit-tiles">
        <div className="habit-tile habit-tile--streak">
          <span className="habit-tile__label">{t.habits.streakTitle}</span>
          <span className="habit-tile__value">
            {t.habits.streakIn(data.streak, data.streak_unit)}
          </span>
        </div>
        <div className="habit-tile">
          <span className="habit-tile__label">{t.habits.record}</span>
          <span className="habit-tile__value">{t.habits.streakIn(data.record, data.streak_unit)}</span>
        </div>
        <div className="habit-tile">
          <span className="habit-tile__label">{t.habits.year}</span>
          <span className="habit-tile__value">{`${data.percent}%`}</span>
        </div>
      </div>

      <Card title={t.habits.yearMap} index={1}>
        <YearMap from={data.year_from} year={data.year} onPickWeek={(monday) => setMonth(monthOfWeek(monday, today, first))} />
      </Card>

      <Card index={2}>
        <div className="month-head">
          <button
            type="button"
            className="icon-button"
            aria-label={t.habits.prevMonth}
            disabled={shown <= first.slice(0, 8) + "01"}
            onClick={() => setMonth(shiftMonth(shown, -1))}
          >
            <ChevronLeft size={18} aria-hidden />
          </button>
          <h2 className="card__title month-head__title">{monthTitle(shown, lang)}</h2>
          <button
            type="button"
            className="icon-button"
            aria-label={t.habits.nextMonth}
            disabled={shown >= `${today.slice(0, 7)}-01`}
            onClick={() => setMonth(shiftMonth(shown, 1))}
          >
            <ChevronRight size={18} aria-hidden />
          </button>
        </div>
        <MonthMarks
          month={shown}
          from={data.year_from}
          year={data.year}
          today={today}
          onToggle={(day, state) => mark.mutate({ id: data.id, day, done: nextDone(state) })}
        />
      </Card>

      <div className="habit-actions">
        <button type="button" className="button button--primary" disabled={share.isPending} onClick={onShare}>
          {t.habits.share}
        </button>
        {write.refused && <WriteRefusedCard text={t.habits.writeText} />}
        <Link href={`/habits/${data.id}/edit`} className="button">{t.habits.edit}</Link>
        <button type="button" className="button button--danger" onClick={() => void onDelete()}>
          {t.habits.deleteButton}
        </button>
      </div>
    </div>
  );
}
