import { useState } from "react";
import { useLocation } from "wouter";
import { useCreateHabit } from "../api/queries";
import { MainAction } from "../components/MainAction";
import { useT } from "../i18n";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_NAME = 50;

export function HabitForm() {
  const t = useT();
  const [, navigate] = useLocation();
  const create = useCreateHabit();
  const [name, setName] = useState("");
  const trimmed = name.trim();
  const valid = trimmed.length > 0 && trimmed.length <= MAX_NAME;
  useClosingConfirmation(trimmed.length > 0);
  useBackButton(() => {
    void (async () => {
      if (!trimmed || (await confirmAction(t.notes.confirmDiscard))) navigate("/habits");
    })();
  });

  const save = () => {
    if (!valid || create.isPending) return;
    create.mutate(trimmed, { onSuccess: () => navigate("/habits") });
  };

  return (
    <>
      <h1 className="screen__title">{t.habits.newTitle}</h1>
      <label className="field">
        <span className="field__label">{t.habits.name}</span>
        <input
          className="input"
          maxLength={MAX_NAME}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <MainAction text={t.common.save} onClick={save} disabled={!valid} busy={create.isPending} />
    </>
  );
}
