import { useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import {
  useAllowWrite,
  useCreateReminder,
  useMe,
  useParseReminder,
  useReminders,
  useUpdateReminder,
} from "../api/queries";
import type { ParsedPhrase, Reminder, ReminderInput } from "../api/types";
import { MainAction } from "../components/MainAction";
import { Empty, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { localTimeHm, localTodayIso, parseIsoDate } from "../lib/format";
import { BOT_CHAT_URL } from "../lib/links";
import { useCityZone } from "../lib/zone";
import {
  confirmAction,
  openTelegramLink,
  requestWriteAccess,
  useBackButton,
  useClosingConfirmation,
} from "../telegram";

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
  monthDay: number;
}

function dayBit(iso: string): number {
  return 1 << ((parseIsoDate(iso).getUTCDay() + 6) % 7);
}

function nextHour(zone: string): string {
  const later = new Date(Date.now() + 60 * 60 * 1000);
  return `${localTimeHm(zone, later).slice(0, 2)}:00`;
}

function blank(date: string, zone: string): Draft {
  return {
    text: "",
    choice: "none",
    date,
    time: nextHour(zone),
    days: dayBit(date),
    monthDay: parseIsoDate(date).getUTCDate(),
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
    monthDay: rule?.month_day ?? parseIsoDate(date).getUTCDate(),
  };
}

function fromParsed(parsed: ParsedPhrase, current: Draft): Draft {
  return {
    ...current,
    text: parsed.text || current.text,
    choice: choiceOf(parsed.repeat, parsed.weekdays, parsed.interval_weeks),
    date: parsed.date ?? current.date,
    time: parsed.time ?? current.time,
    days: parsed.weekdays ?? current.days,
    monthDay: parsed.month_day ?? current.monthDay,
  };
}

function toBody(draft: Draft): ReminderInput {
  const text = draft.text.trim();
  const time_local = draft.time;
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
      return { text, rule: { repeat: "monthly", time_local, month_day: draft.monthDay } };
  }
}

export function ReminderForm() {
  const t = useT();
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
  const allowWrite = useAllowWrite();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [phrase, setPhrase] = useState("");
  const [refused, setRefused] = useState(false);

  const existing = id === null ? undefined : reminders.data?.find((item) => item.id === id);
  const initial =
    existing !== undefined
      ? fromReminder(existing, zone)
      : blank(newParams?.date ?? localTodayIso(zone), zone);
  const current = draft ?? initial;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(initial);
  const change = (patch: Partial<Draft>) => setDraft({ ...current, ...patch });
  const busy = create.isPending || update.isPending || allowWrite.isPending;
  const trimmed = current.text.trim();
  const valid =
    trimmed.length > 0 &&
    trimmed.length <= MAX_TEXT &&
    /^\d{2}:\d{2}$/.test(current.time) &&
    (current.choice !== "none" || current.date !== "") &&
    (!["days", "biweekly"].includes(current.choice) || current.days > 0);

  useClosingConfirmation(dirty);
  useBackButton(() => {
    void (async () => {
      if (!dirty || (await confirmAction(t.reminderForm.confirmDiscard))) navigate("/calendar");
    })();
  });

  if (id !== null && reminders.isPending) return <Loader />;
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
    parse.mutate(phrase, { onSuccess: (parsed) => setDraft(fromParsed(parsed, current)) });
  };

  const save = async () => {
    if (!valid || busy) return;
    if (me.data && !me.data.can_write) {
      if (!(await requestWriteAccess())) {
        setRefused(true);
        return;
      }
      await allowWrite.mutateAsync();
    }
    const done = {
      onSuccess: () => {
        toast({ kind: "success", text: t.reminderForm.saved });
        navigate("/calendar");
      },
    };
    const body = toBody(current);
    if (id === null) create.mutate(body, done);
    else update.mutate({ id, body }, done);
  };

  const showDate = current.choice === "none" || current.choice === "biweekly";
  const showDays = current.choice === "days" || current.choice === "biweekly";

  return (
    <>
      <h1 className="screen__title">{id === null ? t.reminderForm.newTitle : t.reminderForm.editTitle}</h1>
      {refused && (
        <div className="card" role="alert">
          <h2 className="card__title">{t.reminderForm.writeTitle}</h2>
          <p>{t.reminderForm.writeText}</p>
          <button type="button" className="button" onClick={() => openTelegramLink(BOT_CHAT_URL)}>
            {t.reminderForm.openChat}
          </button>
        </div>
      )}
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
        <button type="button" className="button" onClick={understand} disabled={parse.isPending}>
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
        <div className="segmented" role="group" aria-label={t.reminderForm.repeats.days}>
          {t.reminderForm.weekdays.map((name, index) => (
            <button
              type="button"
              key={name}
              className="segmented__option"
              aria-pressed={(current.days & (1 << index)) !== 0}
              onClick={() => change({ days: current.days ^ (1 << index) })}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      <div className="row">
        {showDate && (
          <label className="field" style={{ flex: 1 }}>
            <span className="field__label">{t.reminderForm.date}</span>
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
              onChange={(event) => change({ monthDay: Math.min(31, Math.max(1, Number(event.target.value) || 1)) })}
            />
          </label>
        )}
        <label className="field" style={{ flex: 1 }}>
          <span className="field__label">{t.reminderForm.time}</span>
          <input className="input" type="time" value={current.time} onChange={(event) => change({ time: event.target.value })} />
        </label>
      </div>
      <MainAction text={t.common.save} onClick={() => void save()} disabled={!valid} busy={busy} />
    </>
  );
}
