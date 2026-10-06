import { X } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useRoute } from "wouter";
import {
  useAddingItems, useAddItem, useClearDone, useCreateNote, useDeleteItem, useNotes, usePinNote, useSetItem,
  useUpdateNote,
} from "../api/queries";
import type { Note, NoteInput } from "../api/types";
import { MainAction } from "../components/MainAction";
import { LinkedText } from "../components/NoteBits";
import { Empty, ErrorState, Loader } from "../components/States";
import { useT } from "../i18n";
import { codePoints } from "../lib/format";
import { findLinks, openAddress } from "../lib/links";
import { cleanItem, MAX_ITEM, MAX_ITEMS, MAX_TEXT } from "../lib/notes";
import { confirmAction, haptic, useBackButton, useClosingConfirmation } from "../telegram";

/** A new note (`/notes/new`) or a saved one (`/notes/:id`). */
export function NoteEditor() {
  const [isNew] = useRoute("/notes/new");
  const [, params] = useRoute<{ id: string }>("/notes/:id");
  return isNew || !params ? <NewNote /> : <SavedNote id={Number(params.id)} />;
}

/** The title and 📌: a tap pins or unpins, as the label says; no 📌 (null) for a note gone meanwhile. */
function EditorHead({ title, pinned, onPin }: { title: string; pinned: boolean | null; onPin: () => void }) {
  const t = useT();
  const label = pinned ? t.notes.unpin : t.notes.pin;
  return (
    <div className="editor-head">
      <h1 className="screen__title">{title}</h1>
      {pinned !== null && (
        <button
          type="button"
          className={pinned ? "pin-toggle pin-toggle--on" : "pin-toggle"}
          aria-label={label}
          title={label}
          onClick={onPin}
        >
          <span aria-hidden>📌</span>
        </button>
      )}
    </div>
  );
}

/**
 * The note's text, counted in characters as the server counts them (code points: an emoji is one);
 * under it, why it cannot be saved yet. A checklist's text is its title, so the field is smaller.
 */
function TextField({
  value, onChange, list, hint,
}: { value: string; onChange: (value: string) => void; list: boolean; hint: string | null }) {
  const t = useT();
  const hintId = useId();
  const length = codePoints(value.trim());
  return (
    <>
      <div className="field">
        {/* Explicit `for`/`id` (rather than nesting the counter inside the label) keeps the
            counter text out of the label's accessible name. */}
        <label className="field__label" htmlFor="note-text">{t.notes.placeholder}</label>
        <textarea
          id="note-text"
          className={list ? "input editor editor--list" : "input editor"}
          value={value}
          aria-invalid={length > MAX_TEXT}
          aria-describedby={hint === null ? undefined : hintId}
          onChange={(event) => onChange(event.target.value)}
        />
        <span className={length > MAX_TEXT ? "field__counter field__counter--over" : "field__counter"}>
          {t.notes.counter(length, MAX_TEXT)}
        </span>
      </div>
      <div aria-live="polite">{hint !== null && <p className="field__hint" id={hintId}>{hint}</p>}</div>
    </>
  );
}

/**
 * The field of a new item and «Добавить». The field empties at once, so the next item can be
 * typed while the last one is on its way; at the limit, or with an item too long, «Добавить» is
 * off and the line under the field says why. Items still on their way (`adding`) take their
 * places at once, but the line speaks of the items shown.
 */
function ItemField({ count, adding = 0, onAdd }: { count: number; adding?: number; onAdd: (text: string) => void }) {
  const t = useT();
  const field = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [draft, setDraft] = useState("");
  const text = cleanItem(draft);
  const length = codePoints(text);
  const full = count >= MAX_ITEMS;
  const long = length > MAX_ITEM;
  const ready = count + adding < MAX_ITEMS && length > 0 && !long;
  const add = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    onAdd(text);
    setDraft("");
    // A tap on «Добавить» took the focus (and the keyboard) away: the next item goes in the field.
    field.current?.focus();
  };
  return (
    <>
      <form className="item-add" onSubmit={add}>
        <input
          ref={field}
          className="input"
          placeholder={t.notes.newItem}
          aria-label={t.notes.newItem}
          aria-invalid={long}
          aria-describedby={full || long ? hintId : undefined}
          enterKeyHint="enter"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" className="button" disabled={!ready}>{t.notes.addItem}</button>
      </form>
      <div aria-live="polite">
        {full ? (
          <p className="muted item-add__note" id={hintId}>{t.notes.itemsLimit(MAX_ITEMS)}</p>
        ) : (
          long && <p className="field__hint item-add__note" id={hintId}>{t.notes.counter(length, MAX_ITEM)}</p>
        )}
      </div>
    </>
  );
}

function RemoveItem({ text, onClick }: { text: string; onClick: () => void }) {
  const t = useT();
  return (
    <button type="button" className="icon-button item__remove" aria-label={t.notes.removeItem(text)} onClick={onClick}>
      <X size={20} aria-hidden />
    </button>
  );
}

interface DraftItem {
  key: number;
  text: string;
}

/**
 * A new note: its text, the items of a checklist (only «×» on them yet) and the 📌 — all of it goes
 * to the server at once, with «Сохранить».
 */
function NewNote() {
  const t = useT();
  const [, navigate] = useLocation();
  const create = useCreateNote();
  const titleId = useId();
  const [text, setText] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [pinned, setPinned] = useState(false);
  const nextKey = useRef(0);

  const trimmed = text.trim();
  const length = codePoints(trimmed);
  const valid = length > 0 && length <= MAX_TEXT;
  // Anything typed or added is asked about before it is left behind.
  const started = trimmed !== "" || items.length > 0;
  const leave = async () => {
    if (!started || (await confirmAction(t.notes.confirmDiscard))) navigate("/notes");
  };
  useClosingConfirmation(started);
  useBackButton(() => void leave());

  const save = () => {
    if (!valid || create.isPending) return;
    const note: NoteInput = { text: trimmed };
    if (items.length > 0) note.items = items.map((item) => item.text);
    if (pinned) note.pinned = true;
    create.mutate(note, { onSuccess: () => navigate("/notes") });
  };
  const add = (item: string) => {
    nextKey.current += 1;
    setItems([...items, { key: nextKey.current, text: item }]);
  };

  return (
    <>
      <EditorHead
        title={t.notes.newTitle}
        pinned={pinned}
        onPin={() => {
          haptic("tap");
          setPinned(!pinned);
        }}
      />
      <TextField
        value={text}
        onChange={setText}
        list={items.length > 0}
        hint={items.length > 0 && length === 0 ? t.notes.needTitle : null}
      />
      <section className="items" aria-labelledby={titleId}>
        <h2 className="field__label" id={titleId}>{t.notes.items}</h2>
        {items.length > 0 && (
          <ul className="items__list">
            {items.map((item) => (
              <li key={item.key} className="item item--draft">
                <span className="item__text"><LinkedText text={item.text} /></span>
                <RemoveItem
                  text={item.text}
                  onClick={() => setItems(items.filter((shown) => shown.key !== item.key))}
                />
              </li>
            ))}
          </ul>
        )}
        <ItemField count={items.length} onAdd={add} />
      </section>
      <MainAction text={t.common.save} onClick={save} disabled={!valid} busy={create.isPending} />
    </>
  );
}

/**
 * A saved note. Its 📌 and its items change at once, each tap a request of its own; «Сохранить»
 * saves the text alone, and leaving asks only about a text not saved.
 */
function SavedNote({ id }: { id: number }) {
  const t = useT();
  const [, navigate] = useLocation();
  const notes = useNotes();
  const update = useUpdateNote();
  const pin = usePinNote();
  const note = notes.data?.find((shown) => shown.id === id);
  const [draft, setDraft] = useState<string | null>(null);

  const original = note?.text ?? "";
  const text = draft ?? original;
  const trimmed = text.trim();
  const length = codePoints(trimmed);
  const dirty = draft !== null && draft !== original;
  const valid = length > 0 && length <= MAX_TEXT;
  const leave = async () => {
    if (!dirty || (await confirmAction(t.notes.confirmDiscard))) navigate("/notes");
  };
  useClosingConfirmation(dirty);
  useBackButton(() => void leave());

  if (notes.isPending) return <Loader />;
  // A failed refresh (after a check, say) keeps the note and the draft on screen.
  if (notes.isLoadingError) return <ErrorState onRetry={() => void notes.refetch()} />;
  // Once the user has started a draft, a background refetch that drops the note (e.g. it was
  // deleted elsewhere) must not swap to the not-found state and silently discard their edits —
  // only show it before any edit was made. Saving then surfaces the API's 404 as the usual
  // "already gone" toast, and the draft stays on screen either way.
  if (!note && draft === null) {
    return (
      <>
        <Empty text={t.errors.not_found} />
        <Link href="/notes" className="button">{t.tabs.notes}</Link>
      </>
    );
  }

  const save = () => {
    if (!valid || !dirty || update.isPending) return;
    update.mutate({ id, text: trimmed }, { onSuccess: () => navigate("/notes") });
  };

  return (
    <>
      <EditorHead
        title={t.notes.editTitle}
        pinned={note?.pinned ?? null}
        onPin={() => {
          if (note) pin.mutate({ id, pinned: !note.pinned });
        }}
      />
      <TextField value={text} onChange={setDraft} list={(note?.items.length ?? 0) > 0} hint={null} />
      {note && <NoteLinks text={note.text} />}
      {note && <SavedItems note={note} />}
      <MainAction text={t.common.save} onClick={save} disabled={!valid || !dirty} busy={update.isPending} />
    </>
  );
}

/**
 * The addresses of the saved text, each a button: the field cannot open them, and the list shows
 * no more than six lines of a note.
 */
function NoteLinks({ text }: { text: string }) {
  const t = useT();
  const titleId = useId();
  const links = findLinks(text);
  if (links.length === 0) return null;
  return (
    <div className="note-links" role="group" aria-labelledby={titleId}>
      <span className="field__label" id={titleId}>{t.notes.links}</span>
      <div className="note-links__list">
        {links.map((link) => (
          <button key={link.url} type="button" className="note-links__link" onClick={() => openAddress(link.url)}>
            {link.text}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * The items of a saved note. A check, a new item, «×» and «Убрать отмеченные» go to the server at
 * once and ask nothing; a new item shows once the server has given it an id, so it can never be
 * checked before it exists.
 */
function SavedItems({ note }: { note: Note }) {
  const t = useT();
  const titleId = useId();
  const add = useAddItem();
  const set = useSetItem();
  const remove = useDeleteItem();
  const clear = useClearDone();
  const adding = useAddingItems(note.id);
  return (
    <section className="items" aria-labelledby={titleId}>
      <h2 className="field__label" id={titleId}>{t.notes.items}</h2>
      {note.items.length > 0 && (
        <ul className="items__list">
          {note.items.map((item) => {
            const textId = `note-item-${item.id}`;
            return (
              <li key={item.id} className={item.done ? "item item--done" : "item"}>
                {/* The text is no <label>: a tap on it checks nothing, and an address in it stays a
                    button of its own (a button inside a label is not valid HTML). */}
                <input
                  type="checkbox"
                  className="item__check"
                  checked={item.done}
                  aria-labelledby={textId}
                  onChange={(event) => set.mutate({ note: note.id, id: item.id, done: event.target.checked })}
                />
                <span className="item__text" id={textId}><LinkedText text={item.text} /></span>
                <RemoveItem text={item.text} onClick={() => remove.mutate({ note: note.id, id: item.id })} />
              </li>
            );
          })}
        </ul>
      )}
      <ItemField count={note.items.length} adding={adding} onAdd={(text) => add.mutate({ note: note.id, text })} />
      {note.items.some((item) => item.done) && (
        <button type="button" className="button items__clear" onClick={() => clear.mutate(note.id)}>
          {t.notes.clearDone}
        </button>
      )}
    </section>
  );
}
