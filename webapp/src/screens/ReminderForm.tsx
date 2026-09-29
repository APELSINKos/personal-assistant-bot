import { useState } from "react";
import { useLocation } from "wouter";
import { useCreateReminder } from "../api/queries";
import { MainAction } from "../components/MainAction";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { localTimeHm, localTodayIso } from "../lib/format";
import { useCityZone } from "../lib/zone";
import { useClosingConfirmation } from "../telegram";

const MAX_TEXT = 200;

function inAnHour(zone: string) {
  const later = new Date(Date.now() + 60 * 60 * 1000);
  return { date: localTodayIso(zone, later), time: `${localTimeHm(zone, later).slice(0, 2)}:00` };
}

export function ReminderForm() {
  const t = useT();
  const zone = useCityZone();
  const [, navigate] = useLocation();
  const create = useCreateReminder();
  const [text, setText] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const suggested = inAnHour(zone);
  const day = date ?? suggested.date;
  const hour = time ?? suggested.time;
  const trimmed = text.trim();
  const valid = trimmed.length > 0 && trimmed.length <= MAX_TEXT && day !== "" && hour !== "";
  useClosingConfirmation(trimmed.length > 0);

  const save = () => {
    if (!valid || create.isPending) return;
    create.mutate(
      { text: trimmed, due_local: `${day}T${hour}` },
      {
        onSuccess: () => {
          toast({ kind: "success", text: t.reminders.saved });
          navigate("/reminders");
        },
      },
    );
  };

  return (
    <>
      <h1 className="screen__title">{t.reminders.newTitle}</h1>
      <label className="field">
        <span className="field__label">{t.reminders.text}</span>
        <textarea
          className="input"
          rows={3}
          maxLength={MAX_TEXT}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <div className="row">
        <label className="field" style={{ flex: 1 }}>
          <span className="field__label">{t.reminders.date}</span>
          <input className="input" type="date" value={day} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span className="field__label">{t.reminders.time}</span>
          <input className="input" type="time" value={hour} onChange={(event) => setTime(event.target.value)} />
        </label>
      </div>
      <MainAction text={t.common.save} onClick={save} disabled={!valid} busy={create.isPending} />
    </>
  );
}
