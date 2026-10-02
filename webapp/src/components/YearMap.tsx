import { useLayoutEffect, useMemo, useRef } from "react";
import { useLang, useT } from "../i18n";
import { addDaysIso, parseIsoDate, rangeLabel } from "../lib/format";
import { yearWeeks } from "../lib/habits";

/**
 * A habit's last 53 weeks, one column a week (Monday on top), opened at this week. It is an
 * overview: its squares are too small to tap one by one, so a tap picks the week's month for
 * the editor below.
 */
export function YearMap(
  { from, year, onPickWeek }: { from: string; year: string; onPickWeek: (monday: string) => void },
) {
  const t = useT();
  const lang = useLang();
  const weeks = useMemo(() => yearWeeks(from, year), [from, year]);
  const scroller = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (element) element.scrollLeft = element.scrollWidth; // this week is the last column
  }, [from]);

  return (
    <div className="year-map" ref={scroller}>
      <div className="year-map__grid">
        {weeks.map((week) => {
          const monday = week[0]?.iso ?? from;
          const first = parseIsoDate(monday);
          // The column holding a month's 1st carries the month's name.
          const label = first.getUTCDate() <= 7 ? t.habits.months[first.getUTCMonth()] : "";
          return (
            <button
              key={monday}
              type="button"
              className="year-map__week"
              aria-label={t.habits.pickWeek(rangeLabel(monday, addDaysIso(monday, 6), lang))}
              onClick={() => onPickWeek(monday)}
            >
              <span className="year-map__month" aria-hidden>{label}</span>
              {week.map((day) => (
                <i key={day.iso} className={`year-map__day year-map__day--${day.state}`} aria-hidden />
              ))}
            </button>
          );
        })}
      </div>
    </div>
  );
}
