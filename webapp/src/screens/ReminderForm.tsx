import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import {
  useCreateReminder,
  useMe,
  useParseReminder,
  useReminders,
  useUpdateReminder,
} from "../api/queries";
import type { ParsedPhrase, Reminder, ReminderInput } from "../api/types";
import { MainAction } from "../components/MainAction";
import { Empty, ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { WriteRefusedCard } from "../components/WriteRefusedCard";
import { useLang, useT } from "../i18n";
import { setCalendarDay } from "../lib/calendarDay";
import { addDaysIso, localTimeHm, localTodayIso, mondayOf, parseIsoDate } from "../lib/format";
import { useWriteAccess } from "../lib/useWriteAccess";
import { useCityZone } from "../lib/zone";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_TEXT = 200;
const WEEKDAYS = 31;
const WEEKENDS = 96;
const CHOICES = ["none", "daily", "weekdays", "weekends", "days", "biweekly", "monthly"] as const;
type Choice = (typeof CHOICES)[number];

interface Draft {
  text: string;
  choice: Choice;
  date: string;
  time: string;
  days: number;
  /** Kept as raw text so the field can be emptied while retyping (see `blank`/`valid`). */
  monthDay: string;
}

function dayBit(iso: string): number {
  return 1 << ((parseIsoDate(iso).getUTCDay() + 6) % 7);
}

/**
 * With no explicit date, both the date and the time default together from "now + 1 hour" — so a
 * default made close to midnight rolls onto the next day instead of showing a past time today.
 */
function blank(date: string | undefined, zone: string): Draft {
  const later = new Date(Date.now() + 60 * 60 * 1000);
  const day = date ?? localTodayIso(zone, later);
  return {
    text: "",
    choice: "none",
    date: day,
    time: `${localTimeHm(zone, later).slice(0, 2)}:00`,
    days: dayBit(day),
    monthDay: String(parseIsoDate(day).getUTCDate()),
  };
}

function choiceOf(repeat: string, weekdays: number | null, interval: number): Choice {
  if (repeat === "daily") return "daily";
  if (repeat === "monthly") return "monthly";
  if (repeat !== "weekly") return "none";
  if (interval === 2) return "biweekly";
  if (weekdays === WEEKDAYS) return "weekdays";
  if (weekdays === WEEKENDS) return "weekends";
  return "days";
}

function fromReminder(reminder: Reminder, zone: string): Draft {
  const [date = "", time = ""] = reminder.due_local.split("T");
  const rule = reminder.rule;
  return {
    ...blank(date, zone),
    text: reminder.text,
    choice: rule ? choiceOf(rule.repeat, rule.weekdays, rule.interval_weeks) : "none",
    date: rule?.interval_weeks === 2 ? rule.anchor_date : date,
    time: rule?.time_local ?? time,
    days: rule?.weekdays ?? dayBit(date),
    monthDay: String(rule?.month_day ?? parseIsoDate(date).getUTCDate()),
  };
}

/** A phrase without a time (e.g. "завтра купить молоко") blanks the time instead of keeping
 * whatever was there before — the bot asks for a time instead of guessing one. */
function fromParsed(parsed: ParsedPhrase, current: Draft): Draft {
  return {
    ...current,
    text: parsed.text || current.text,
    choice: choiceOf(parsed.repeat, parsed.weekdays, parsed.interval_weeks),
    date: parsed.date ?? current.date,
    time: parsed.time ?? "",
    days: parsed.weekdays ?? current.days,
    monthDay: String(parsed.month_day ?? current.monthDay),
  };
}

function toBody(draft: Draft): ReminderInput {
  const text = draft.text.trim();
  const time_local = draft.time;
  const monthDay = Number.parseInt(draft.monthDay, 10);
  switch (draft.choice) {
    case "none":
      return { text, due_local: `${draft.date}T${draft.time}` };
    case "daily":
      return { text, rule: { repeat: "daily", time_local } };
    case "weekdays":
      return { text, rule: { repeat: "weekly", time_local, weekdays: WEEKDAYS } };
    case "weekends":
      return { text, rule: { repeat: "weekly", time_local, weekdays: WEEKENDS } };
    case "days":
      return { text, rule: { repeat: "weekly", time_local, weekdays: draft.days } };
    case "biweekly":
      return {
        text,
        rule: { repeat: "weekly", time_local, weekdays: draft.days, interval_weeks: 2, anchor_date: draft.date },
      };
    case "monthly":
      return { text, rule: { repeat: "monthly", time_local, month_day: monthDay } };
  }
}

export function ReminderForm() {
  const t = useT();
  const lang = useLang();
  const zone = useCityZone();
  const [, navigate] = useLocation();
  const [isNew, newParams] = useRoute<{ date?: string }>("/calendar/new/:date?");
  const [, editParams] = useRoute<{ id: string }>("/calendar/:id");
  const id = isNew || !editParams ? null : Number(editParams.id);
  const me = useMe();
  const reminders = useReminders();
  const create = useCreateReminder();
  const update = useUpdateReminder();
  const parse = useParseReminder();
  const write = useWriteAccess(me.data?.can_write);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [phrase, setPhrase] = useState("");
  const timeRef = useRef<HTMLInputElement>(null);

  const existing = id === null ? undefined : reminders.data?.find((item) => item.id === id);
  // Memoised so a brand new reminder's default date/time (`blank`) is computed once — while the
  // user is filling the form it should not keep drifting forward with the wall clock.
  const initial = useMemo(
    () => (existing !== undefined ? fromReminder(existing, zone) : blank(newParams?.date, zone)),
    [existing, newParams?.date, zone],
  );
  const initialRef = useRef(initial);
  useEffect(() => {
    initialRef.current = initial;
  });
  const current = draft ?? initial;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(initial);
  const change = (patch: Partial<Draft>) => setDraft({ ...current, ...patch });
  const busy = create.isPending || update.isPending || write.pending;
  const trimmed = current.text.trim();
  const showDate = current.choice === "none" || current.choice === "biweekly";
  const showDays = current.choice === "days" || current.choice === "biweekly";
  const monthDayNum = Number(current.monthDay);
  const monthDayValid =
    current.choice !== "monthly" ||
    (current.monthDay !== "" && Number.isInteger(monthDayNum) && monthDayNum >= 1 && monthDayNum <= 31);
  const valid =
    trimmed.length > 0 &&
    trimmed.length <= MAX_TEXT &&
    /^\d{2}:\d{2}$/.test(current.time) &&
    (!showDate || current.date !== "") &&
    (!showDays || current.days > 0) &&
    monthDayValid;
  const weekStart = mondayOf(localTodayIso(zone));
  const weekdayLabel = (index: number) =>
    new Intl.DateTimeFormat(lang, { timeZone: "UTC", weekday: "long" }).format(
      parseIsoDate(addDaysIso(weekStart, index)),
    );

  useClosingConfirmation(dirty);
  useBackButton(() => {
    void (async () => {
      if (!dirty || (await confirmAction(t.reminderForm.confirmDiscard))) navigate("/calendar");
    })();
  });

  if (id !== null && reminders.isPending) return <Loader />;
  if (id !== null && reminders.isError) {
    return (
      <>
        <h1 className="screen__title">{t.reminderForm.editTitle}</h1>
        <ErrorState onRetry={() => void reminders.refetch()} />
      </>
    );
  }
  if (id !== null && !existing) {
    return (
      <>
        <Empty text={t.errors.not_found} />
        <Link href="/calendar" className="button">{t.calendar.title}</Link>
      </>
    );
  }

  const understand = () => {
    if (!phrase.trim() || parse.isPending) return;
    parse.mutate(phrase, {
      onSuccess: (parsed) => {
        // A functional update: merges onto whatever the user has typed by the time the phrase
        // comes back, not onto a stale snapshot taken when "Понять" was pressed.
        setDraft((prevDraft) => fromParsed(parsed, prevDraft ?? initialRef.current));
        if (parsed.time === null) timeRef.current?.focus();
      },
    });
  };

  const save = async () => {
    if (!valid || busy) return;
    if (!(await write.ensure())) return;
    const done = {
      onSuccess: (saved: Reminder) => {
        setCalendarDay(saved.due_local.slice(0, 10));
        toast({ kind: "success", text: t.reminderForm.saved });
        navigate("/calendar");
      },
    };
    const body = toBody(current);
    if (id === null) create.mutate(body, done);
    else update.mutate({ id, body }, done);
  };

  return (
    <>
      <h1 className="screen__title">{id === null ? t.reminderForm.newTitle : t.reminderForm.editTitle}</h1>
      {write.refused && <WriteRefusedCard />}
      <div className="row field">
        <input
          className="input"
          style={{ flex: 1 }}
          aria-label={t.reminderForm.phrase}
          placeholder={t.reminderForm.phrase}
          maxLength={MAX_TEXT + 100}
          value={phrase}
          onChange={(event) => setPhrase(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") understand();
          }}
        />
        <button
          type="button"
          className="button"
          onClick={understand}
          disabled={parse.isPending}
          aria-busy={parse.isPending}
        >
          {t.reminderForm.understand}
        </button>
      </div>
      <label className="field">
        <span className="field__label">{t.reminderForm.text}</span>
        <textarea
          className="input"
          rows={2}
          maxLength={MAX_TEXT}
          value={current.text}
          onChange={(event) => change({ text: event.target.value })}
        />
      </label>
      <div className="field">
        <span className="field__label">{t.reminderForm.repeat}</span>
        <div className="segmented segmented--wrap" role="group" aria-label={t.reminderForm.repeat}>
          {CHOICES.map((choice) => (
            <button
              type="button"
              key={choice}
              className="segmented__option"
              aria-pressed={current.choice === choice}
              onClick={() => change({ choice })}
            >
              {t.reminderForm.repeats[choice]}
            </button>
          ))}
        </div>
      </div>
      {showDays && (
        <>
          <div className="segmented segmented--week" role="group" aria-label={t.reminderForm.repeats.days}>
            {t.reminderForm.weekdays.map((name, index) => (
              <button
                type="button"
                key={name}
                className="segmented__option"
                aria-pressed={(current.days & (1 << index)) !== 0}
                aria-label={weekdayLabel(index)}
                onClick={() => change({ days: current.days ^ (1 << index) })}
              >
                {name}
              </button>
            ))}
          </div>
          {current.days === 0 && (
            <p className="field__hint" role="alert">{t.errors.repeat_invalid}</p>
          )}
        </>
      )}
      <div className="row">
        {showDate && (
          <label className="field" style={{ flex: 1 }}>
            <span className="field__label">
              {current.choice === "biweekly" ? t.reminderForm.firstDate : t.reminderForm.date}
            </span>
            <input className="input" type="date" value={current.date} onChange={(event) => change({ date: event.target.value })} />
          </label>
        )}
        {current.choice === "monthly" && (
          <label className="field" style={{ flex: 1 }}>
            <span className="field__label">{t.reminderForm.monthDay}</span>
            <input
              className="input"
              type="number"
              min={1}
              max={31}
              value={current.monthDay}
              onChange={(event) => change({ monthDay: event.target.value })}
            />
          </label>
        )}
        <div style={{ flex: 1 }}>
          <label className="field">
            <span className="field__label">{t.reminderForm.time}</span>
            <input
              ref={timeRef}
              className="input"
              type="time"
              value={current.time}
              onChange={(event) => change({ time: event.target.value })}
            />
          </label>
          {/* A sibling of the label, not inside it — nesting it would fold this text into the
              input's accessible name via the implicit label association. */}
          {current.time === "" && <p className="field__hint" role="alert">{t.errors.needs_time}</p>}
        </div>
      </div>
      <MainAction text={t.common.save} onClick={() => void save()} disabled={!valid} busy={busy} />
    </>
  );
}
