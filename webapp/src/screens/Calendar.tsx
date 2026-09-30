import { ChevronLeft, ChevronRight } from "lucide-react";
import { useRef, useState, type TouchEvent } from "react";
import { Link } from "wouter";
import { useAgenda, useDeleteReminder, useMe } from "../api/queries";
import type { AgendaDay, AgendaItem } from "../api/types";
import { Fab } from "../components/Fab";
import { ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useLang, useT } from "../i18n";
import { getCalendarDay, setCalendarDay } from "../lib/calendarDay";
import {
  addDaysIso,
  dayHeading,
  dayNumber,
  localTodayIso,
  monthGrid,
  monthTitle,
  rangeLabel,
  weekOf,
  weekdayShort,
} from "../lib/format";
import { confirmAction, haptic } from "../telegram";

const SWIPE_PX = 50;

function itemsOn(days: AgendaDay[] | undefined, iso: string): AgendaItem[] {
  return days?.find((day) => day.date === iso)?.items ?? [];
}

/** The week's days sliced out of an already-loaded month range, when it covers every one of them. */
function weekDaysFrom(monthDays: AgendaDay[] | undefined, weekIsos: string[]): AgendaDay[] | undefined {
  if (!monthDays) return undefined;
  const byDate = new Map(monthDays.map((entry) => [entry.date, entry]));
  return weekIsos.every((iso) => byDate.has(iso)) ? weekIsos.map((iso) => byDate.get(iso) as AgendaDay) : undefined;
}

function Dots({ items }: { items: AgendaItem[] }) {
  return (
    <span className="cal-dots" aria-hidden>
      {items.slice(0, 3).map((item) => (
        <i key={`${item.id}-${item.time}`} className="cal-dot" />
      ))}
    </span>
  );
}

export function CalendarScreen() {
  const t = useT();
  const lang = useLang();
  const me = useMe();
  const remove = useDeleteReminder();
  const [picked, setPicked] = useState<string | null>(() => getCalendarDay());
  const [monthOpen, setMonthOpen] = useState(false);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);

  const zone = me.data?.city.timezone;
  const today = zone ? localTodayIso(zone) : "";
  const day = picked ?? today;
  const week = day ? weekOf(day) : [];
  const grid = day ? monthGrid(day) : [];
  const agenda = useAgenda(week[0] ?? "", week[6] ?? "", day !== "");
  const month = useAgenda(grid[0]?.[0] ?? "", grid.at(-1)?.[6] ?? "", monthOpen && day !== "");

  if (me.isError) return <ErrorState onRetry={() => void me.refetch()} />;
  if (!day) return <Loader />;

  // While the week itself hasn't loaded, an already-fetched month range that covers it (e.g. the
  // user just picked a day from the open month) stands in at once; the week keeps fetching quietly.
  const days = agenda.data?.days ?? weekDaysFrom(month.data?.days, week);
  const dayItems = itemsOn(days, day);
  const heading = (iso: string) => dayHeading(iso, today, lang, t.calendar.words);
  const monthLabel = (iso: string) => {
    const items = month.data ? itemsOn(month.data.days, iso) : undefined;
    if (!items) return heading(iso);
    return `${heading(iso)}, ${items.length ? t.calendar.count(items.length) : t.calendar.empty}`;
  };
  const pick = (iso: string) => {
    const value = iso === today ? null : iso;
    setPicked(value);
    setCalendarDay(value);
    haptic("select");
  };
  const shiftWeek = (weeks: number) => pick(addDaysIso(day, 7 * weeks));
  const cellClass = (iso: string, other = false) =>
    ["cal-cell", iso === day && "cal-cell--selected", iso === today && "cal-cell--today", other && "cal-cell--other"]
      .filter(Boolean)
      .join(" ");
  const onDelete = async (item: AgendaItem) => {
    const question =
      item.repeat === "none" ? t.calendar.confirmDelete : t.calendar.confirmDeleteSeries(item.text);
    if (await confirmAction(question)) remove.mutate(item.id);
  };
  const onTouchStart = (event: TouchEvent) => {
    const touch = event.touches[0];
    swipeStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
  };
  const onTouchEnd = (event: TouchEvent) => {
    const start = swipeStart.current;
    const touch = event.changedTouches[0];
    swipeStart.current = null;
    if (!start || !touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) >= SWIPE_PX && Math.abs(dx) > Math.abs(dy)) shiftWeek(dx < 0 ? 1 : -1);
  };

  return (
    <>
      <div className="cal-head">
        <h1 className="screen__title">
          <button
            type="button"
            className="cal-title"
            aria-expanded={monthOpen}
            onClick={() => setMonthOpen((open) => !open)}
          >
            {t.calendar.title}{" "}
            <span className="visually-hidden">{monthOpen ? t.calendar.hideMonth : t.calendar.showMonth}</span>
          </button>
        </h1>
        {day !== today && (
          <button
            type="button"
            className="chip-button"
            onClick={() => {
              setPicked(null);
              setCalendarDay(null);
              setMonthOpen(false);
            }}
          >
            {t.calendar.today}
          </button>
        )}
      </div>

      <div className="cal-range">
        <button type="button" className="icon-button" aria-label={t.calendar.prevWeek} onClick={() => shiftWeek(-1)}>
          <ChevronLeft size={18} aria-hidden />
        </button>
        <span className="muted">{rangeLabel(week[0] ?? day, week[6] ?? day, lang)}</span>
        <button type="button" className="icon-button" aria-label={t.calendar.nextWeek} onClick={() => shiftWeek(1)}>
          <ChevronRight size={18} aria-hidden />
        </button>
      </div>

      {monthOpen ? (
        <div className="cal-month">
          <div className="cal-month__title">{monthTitle(day, lang)}</div>
          <div className="cal-month__weekdays">
            {(grid[0] ?? []).map((iso) => (
              <span key={iso} className="cal-cell__weekday">
                {weekdayShort(iso, lang)}
              </span>
            ))}
          </div>
          {grid.map((row) => (
            <div key={row[0]} className="cal-month__row">
              {row.map((iso) => (
                <button
                  key={iso}
                  type="button"
                  className={cellClass(iso, iso.slice(0, 7) !== day.slice(0, 7))}
                  aria-pressed={iso === day}
                  aria-current={iso === today ? "date" : undefined}
                  aria-label={monthLabel(iso)}
                  onClick={() => {
                    pick(iso);
                    setMonthOpen(false);
                  }}
                >
                  <span className="cal-cell__mark">{dayNumber(iso)}</span>
                  <Dots items={itemsOn(month.data?.days, iso)} />
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="cal-strip" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
          {week.map((iso) => (
            <button
              key={iso}
              type="button"
              className={cellClass(iso)}
              aria-label={heading(iso)}
              aria-pressed={iso === day}
              aria-current={iso === today ? "date" : undefined}
              onClick={() => pick(iso)}
            >
              <span className="cal-cell__weekday">{weekdayShort(iso, lang)}</span>
              <span className="cal-cell__day">{dayNumber(iso)}</span>
              <Dots items={itemsOn(days, iso)} />
            </button>
          ))}
        </div>
      )}

      <div className="cal-dayhead">
        <h2 className="cal-dayhead__title">{heading(day)}</h2>
        {!agenda.isError && days && (
          <p className="muted">{dayItems.length ? t.calendar.count(dayItems.length) : t.calendar.empty}</p>
        )}
      </div>

      {agenda.isError ? (
        <ErrorState onRetry={() => void agenda.refetch()} />
      ) : !days ? (
        <Loader />
      ) : (
        dayItems.map((item) => (
          <SwipeRow key={`${item.id}-${item.time}`} onDelete={() => void onDelete(item)} deleteLabel={t.calendar.delete}>
            <Link href={`/calendar/${item.id}`} className="cal-item">
              <span className="time">{item.time}</span>
              <span className="cal-item__body">
                <span className="cal-item__text">
                  {item.repeat !== "none" ? "↻ " : ""}
                  {item.text}
                </span>
                {item.description && <span className="muted cal-item__sub">{item.description}</span>}
              </span>
            </Link>
          </SwipeRow>
        ))
      )}
      <Fab href={`/calendar/new/${day}`} label={t.calendar.add} />
    </>
  );
}
