import { Check, X } from "lucide-react";
import { useLang, useT } from "../i18n";
import { dayMonth, dayNumber, monthGrid, monthTitle, weekdayShort } from "../lib/format";
import { type DayState, stateOn } from "../lib/habits";

/**
 * One month of a habit, a day a button: a tap moves the day's mark along ⬜ → ✅ → ❌ → ⬜.
 * Days before the habit began and days ahead cannot be marked.
 */
export function MonthMarks({
  month, from, year, today, onToggle,
}: {
  /** Any day of the month to show. */
  month: string;
  from: string;
  year: string;
  today: string;
  onToggle: (day: string, state: DayState) => void;
}) {
  const t = useT();
  const lang = useLang();
  const grid = monthGrid(month);
  const stateName = (state: DayState) =>
    state === "done" ? t.habits.state.done : state === "missed" ? t.habits.state.skipped : t.habits.state.none;

  return (
    <div className="month-marks" role="group" aria-label={monthTitle(month, lang)}>
      <div className="month-marks__row month-marks__weekdays" aria-hidden>
        {(grid[0] ?? []).map((iso) => (
          <span key={iso}>{weekdayShort(iso, lang)}</span>
        ))}
      </div>
      {grid.map((week) => (
        <div key={week[0]} className="month-marks__row">
          {week.map((iso) => {
            if (iso.slice(0, 7) !== month.slice(0, 7)) {
              return <span key={iso} className="month-marks__cell month-marks__cell--other" aria-hidden />;
            }
            const state = stateOn(from, year, iso);
            const classes = ["month-marks__cell", `month-marks__cell--${state}`];
            if (iso === today) classes.push("month-marks__cell--today");
            if (state === "outside") {
              // Shown, but not offered to a screen reader: every day it can mark is a button
              // that names its full date.
              return (
                <span key={iso} className={classes.join(" ")} aria-hidden>
                  {dayNumber(iso)}
                </span>
              );
            }
            return (
              <button
                key={iso}
                type="button"
                className={classes.join(" ")}
                aria-label={t.habits.dayToggle(dayMonth(iso, lang), stateName(state))}
                aria-current={iso === today ? "date" : undefined}
                onClick={() => onToggle(iso, state)}
              >
                <span className="month-marks__number">{dayNumber(iso)}</span>
                {state === "done" && <Check size={14} aria-hidden />}
                {state === "missed" && <X size={14} aria-hidden />}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
