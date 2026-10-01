import { ChevronLeft, ChevronRight } from "lucide-react";
import { useRef, useState, type TouchEvent } from "react";
import { Link } from "wouter";
import { useAgenda, useDeleteReminder, useMe } from "../api/queries";
import type { AgendaDay, AgendaItem, LessonItem, ReminderItem } from "../api/types";
import { Fab } from "../components/Fab";
import { ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useLang, useT } from "../i18n";
import { getCalendarDay, setCalendarDay } from "../lib/calendarDay";
import {
  addDaysIso,
  dayHeading,
  dayNumber,
  lessonMeta,
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

/** The timetable's week label for a day. It belongs to a date range, so a window can hold two;
 *  a day outside every range borrows the window's first label. */
function labelOn(days: AgendaDay[] | undefined, iso: string): string | null {
  return days?.find((day) => day.date === iso)?.label || days?.find((day) => day.label)?.label || null;
}

/** The week's days sliced out of an already-loaded month range, when it covers every one of them. */
function weekDaysFrom(monthDays: AgendaDay[] | undefined, weekIsos: string[]): AgendaDay[] | undefined {
  if (!monthDays) return undefined;
  const byDate = new Map(monthDays.map((entry) => [entry.date, entry]));
  return weekIsos.every((iso) => byDate.has(iso)) ? weekIsos.map((iso) => byDate.get(iso) as AgendaDay) : undefined;
}

const MAX_DOTS = 3;

/** At most three dots, lessons first. When a day has both kinds the lessons take at most two of them,
 *  so a reminder is never hidden behind a full day of classes. */
function Dots({ items }: { items: AgendaItem[] }) {
  const lessons = items.filter((item) => item.kind === "lesson").length;
  const reminders = items.length - lessons;
  const lessonDots = Math.min(lessons, reminders > 0 ? MAX_DOTS - 1 : MAX_DOTS);
  const reminderDots = Math.min(reminders, MAX_DOTS - lessonDots);
  return (
    <span className="cal-dots" aria-hidden>
      {Array.from({ length: lessonDots }, (_, index) => (
        <i key={`lesson-${index}`} className="cal-dot cal-dot--lesson" />
      ))}
      {Array.from({ length: reminderDots }, (_, index) => (
        <i key={`reminder-${index}`} className="cal-dot" />
      ))}
    </span>
  );
}

/** A lesson from the timetable: read-only, so a plain card — no link, no swipe to delete. */
function LessonRow({ lesson }: { lesson: LessonItem }) {
  return (
    <div className="cal-item cal-lesson">
      <span className="time">{lesson.time}</span>
      <span className="cal-item__body">
        <span className="cal-item__text">{lesson.title}</span>
        <span className="muted cal-item__sub">
          {lessonMeta(lesson.lesson_kind, lesson.time, lesson.end, lesson.room)}
        </span>
      </span>
    </div>
  );
}

/** A reminder: a link to its editor in a row that swipes (or, with a mouse, clicks) to delete. */
function ReminderRow({ reminder, onDelete }: { reminder: ReminderItem; onDelete: () => void }) {
  const t = useT();
  return (
    <SwipeRow onDelete={onDelete} deleteLabel={t.calendar.delete}>
      <Link href={`/calendar/${reminder.id}`} className="cal-item">
        <span className="time">{reminder.time}</span>
        <span className="cal-item__body">
          <span className="cal-item__text">
            {reminder.repeat !== "none" ? "↻ " : ""}
            {reminder.text}
          </span>
          {reminder.description && <span className="muted cal-item__sub">{reminder.description}</span>}
        </span>
      </Link>
    </SwipeRow>
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
  const weekLabel = labelOn(days, day);
  const heading = (iso: string) => dayHeading(iso, today, lang, t.calendar.words);
  /** «2 пары · 1 напоминание», or «Ничего не запланировано». */
  const summary = (items: AgendaItem[]) => {
    const lessons = items.filter((item) => item.kind === "lesson").length;
    const reminders = items.length - lessons;
    const parts = [
      lessons ? t.calendar.lessons(lessons) : "",
      reminders ? t.calendar.count(reminders) : "",
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : t.calendar.empty;
  };
  const monthLabel = (iso: string) => {
    const items = month.data ? itemsOn(month.data.days, iso) : undefined;
    return items ? `${heading(iso)}, ${summary(items)}` : heading(iso);
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
  const onDelete = async (item: ReminderItem) => {
    const question =
      item.repeat === "none" ? t.calendar.confirmDelete : t.calendar.confirmDeleteSeries(item.text);
    if (await confirmAction(question)) remove.mutate(item.id);
  };
  const row = (item: AgendaItem, index: number) =>
    item.kind === "lesson" ? (
      <LessonRow key={`lesson-${item.time}-${index}`} lesson={item} />
    ) : (
      <ReminderRow key={`${item.id}-${item.time}`} reminder={item} onDelete={() => void onDelete(item)} />
    );
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
        <span className="muted">
          {weekLabel ? `${weekLabel} · ` : ""}
          {rangeLabel(week[0] ?? day, week[6] ?? day, lang)}
        </span>
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
          <p className="muted">{summary(dayItems)}</p>
        )}
      </div>

      {agenda.isError ? (
        <ErrorState onRetry={() => void agenda.refetch()} />
      ) : !days ? (
        <Loader />
      ) : (
        dayItems.map(row)
      )}
      <Fab href={`/calendar/new/${day}`} label={t.calendar.add} />
    </>
  );
}
