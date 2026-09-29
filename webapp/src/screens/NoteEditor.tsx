import { useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import { useCreateNote, useNotes, useUpdateNote } from "../api/queries";
import { MainAction } from "../components/MainAction";
import { Empty, ErrorState, Loader } from "../components/States";
import { useT } from "../i18n";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_TEXT = 500;

export function NoteEditor() {
  const t = useT();
  const [, navigate] = useLocation();
  const [isNew] = useRoute("/notes/new");
  const [, params] = useRoute<{ id: string }>("/notes/:id");
  const id = isNew || !params ? null : Number(params.id);
  const notes = useNotes();
  const create = useCreateNote();
  const update = useUpdateNote();
  const existing = id === null ? undefined : notes.data?.find((note) => note.id === id);
  const [draft, setDraft] = useState<string | null>(null);

  const original = existing?.text ?? "";
  const text = draft ?? original;
  const trimmed = text.trim();
  const dirty = draft !== null && draft !== original;
  const valid = trimmed.length > 0 && trimmed.length <= MAX_TEXT;
  const leave = async () => {
    if (!dirty || (await confirmAction(t.notes.confirmDiscard))) navigate("/notes");
  };
  useClosingConfirmation(dirty);
  useBackButton(() => void leave());

  if (id !== null && notes.isPending) return <Loader />;
  if (id !== null && notes.isError) return <ErrorState onRetry={() => void notes.refetch()} />;
  // Once the user has started a draft, a background refetch that drops the note (e.g. it was
  // deleted elsewhere) must not swap to the not-found state and silently discard their edits —
  // only show it before any edit was made. Saving then surfaces the API's 404 as the usual
  // "already gone" toast, and the draft stays on screen either way.
  if (id !== null && !existing && draft === null) {
    return (
      <>
        <Empty text={t.errors.not_found} />
        <Link href="/notes" className="button">{t.tabs.notes}</Link>
      </>
    );
  }

  const save = () => {
    if (!valid || !dirty || create.isPending || update.isPending) return;
    const done = { onSuccess: () => navigate("/notes") };
    if (id === null) create.mutate(trimmed, done);
    else update.mutate({ id, text: trimmed }, done);
  };

  return (
    <>
      <h1 className="screen__title">{id === null ? t.notes.newTitle : t.notes.editTitle}</h1>
      <div className="field">
        {/* Explicit `for`/`id` (rather than nesting the counter inside the label) keeps the
            counter text out of the label's accessible name. */}
        <label className="field__label" htmlFor="note-text">{t.notes.placeholder}</label>
        <textarea
          id="note-text"
          className="input editor"
          maxLength={MAX_TEXT}
          value={text}
          onChange={(event) => setDraft(event.target.value)}
        />
        <span className="field__counter">{t.notes.counter(text.length, MAX_TEXT)}</span>
      </div>
      <MainAction
        text={t.common.save}
        onClick={save}
        disabled={!valid || !dirty}
        busy={create.isPending || update.isPending}
      />
    </>
  );
}
