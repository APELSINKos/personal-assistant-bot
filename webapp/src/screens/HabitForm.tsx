import { type CSSProperties, useState } from "react";
import { useLocation, useRoute } from "wouter";
import { isGone, useCreateHabit, useHabit, useUpdateHabit } from "../api/queries";
import type { HabitColor } from "../api/types";
import { HabitLoadError } from "../components/HabitBits";
import { MainAction } from "../components/MainAction";
import { Loader } from "../components/States";
import { useTextLimit } from "../components/TextLimit";
import { useT } from "../i18n";
import { COLORS, DAILY, EMOJI } from "../lib/habits";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_NAME = 50;
const GOALS = [DAILY, 6, 5, 4, 3, 2, 1];

interface Draft {
  name: string;
  emoji: string;
  color: HabitColor;
  goal: number;
}

const BLANK: Draft = { name: "", emoji: "🎯", color: "mint", goal: DAILY };

/** A new habit (/habits/new) or an existing one's name, look and goal (/habits/:id/edit). */
export function HabitForm() {
  const t = useT();
  const [, navigate] = useLocation();
  const [, params] = useRoute<{ id: string }>("/habits/:id/edit");
  const id = params ? Number(params.id) : null;
  const habit = useHabit(id ?? 0, id !== null);
  const create = useCreateHabit();
  const update = useUpdateHabit();
  const [draft, setDraft] = useState<Draft | null>(null);

  const initial: Draft = habit.data
    ? { name: habit.data.name, emoji: habit.data.emoji, color: habit.data.color, goal: habit.data.weekly_goal }
    : BLANK;
  const current = draft ?? initial;
  const change = (patch: Partial<Draft>) => setDraft({ ...current, ...patch });
  const trimmed = current.name.trim();
  const nameLimit = useTextLimit(trimmed, MAX_NAME);
  const valid = trimmed !== "" && !nameLimit.over;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(initial);
  const back = id === null ? "/habits" : `/habits/${id}`;
  const busy = create.isPending || update.isPending;

  useClosingConfirmation(id === null ? trimmed !== "" : dirty);
  useBackButton(() => {
    void (async () => {
      const unsaved = id === null ? trimmed !== "" : dirty;
      if (!unsaved || (await confirmAction(t.notes.confirmDiscard))) navigate(back);
    })();
  });

  // A failed refresh keeps the form and its draft: only a first load that failed is an error, and a
  // refresh that finds the habit deleted meanwhile says so.
  if (id !== null && (habit.isLoadingError || isGone(habit.error))) {
    return <HabitLoadError error={habit.error} onRetry={() => void habit.refetch()} />;
  }
  if (id !== null && habit.isPending) return <Loader />;

  const save = () => {
    if (!valid || busy) return;
    const look = { name: trimmed, emoji: current.emoji, color: current.color, weekly_goal: current.goal };
    if (id === null) create.mutate(look, { onSuccess: () => navigate("/habits") });
    else update.mutate({ id, patch: look }, { onSuccess: () => navigate(back) });
  };

  return (
    <>
      <h1 className="screen__title">{id === null ? t.habits.newTitle : t.habits.editTitle}</h1>
      <label className="field">
        <span className="field__label">{t.habits.name}</span>
        <input
          className="input"
          value={current.name}
          {...nameLimit.field}
          onChange={(event) => change({ name: event.target.value })}
        />
      </label>
      {nameLimit.hint}

      <div className="field">
        <span className="field__label" id="habit-emoji">{t.habits.emoji}</span>
        <div className="emoji-grid" role="group" aria-labelledby="habit-emoji">
          {EMOJI.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className="emoji-grid__item"
              aria-pressed={current.emoji === emoji}
              onClick={() => change({ emoji })}
            >
              {emoji}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label" id="habit-color">{t.habits.color}</span>
        <div className="color-row" role="group" aria-labelledby="habit-color">
          {COLORS.map((color) => (
            <button
              key={color}
              type="button"
              className="color-dot"
              style={{ "--habit": `var(--habit-${color})` } as CSSProperties}
              aria-label={t.habits.colors[color]}
              aria-pressed={current.color === color}
              onClick={() => change({ color })}
            />
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label" id="habit-goal">{t.habits.goal}</span>
        <div className="segmented segmented--wrap" role="group" aria-labelledby="habit-goal">
          {GOALS.map((goal) => (
            <button
              key={goal}
              type="button"
              className="segmented__option"
              aria-pressed={current.goal === goal}
              onClick={() => change({ goal })}
            >
              {goal === DAILY ? t.habits.goalDaily : t.habits.goalWeekly(goal)}
            </button>
          ))}
        </div>
        <div aria-live="polite">
          {id !== null && current.goal !== initial.goal && <p className="muted field__note">{t.habits.goalHint}</p>}
        </div>
      </div>

      <MainAction text={t.common.save} onClick={save} disabled={!valid} busy={busy} />
    </>
  );
}
