import { Fragment, type CSSProperties } from "react";
import { useT } from "../i18n";
import { linkParts, openAddress } from "../lib/links";

/**
 * A note's text, or an item's, with each address in it a button that opens it: a t.me one inside
 * Telegram, any other in the browser. Buttons, not links: a card or an item row around them may
 * open or check something of its own, and a tap on an address must do only what it says.
 */
export function LinkedText({ text }: { text: string }) {
  return (
    <>
      {linkParts(text).map((part, place) => {
        const url = part.url;
        if (url === null) return <Fragment key={place}>{part.text}</Fragment>;
        return (
          <button key={place} type="button" className="note-link" onClick={() => openAddress(url)}>
            {part.text}
          </button>
        );
      })}
    </>
  );
}

/**
 * A checklist's progress, «✅ 2/5», read out as «Отмечено 2 из 5»; with `bar`, a thin bar of it as
 * well, for the eye only.
 */
export function NoteProgress({ done, total, bar = false }: { done: number; total: number; bar?: boolean }) {
  const t = useT();
  return (
    <span className="note-progress">
      <span className="note-progress__count" aria-hidden>{t.notes.progress(done, total)}</span>
      <span className="visually-hidden">{t.notes.progressLabel(done, total)}</span>
      {bar && (
        <span className="note-progress__bar" aria-hidden>
          <span className="note-progress__done" style={{ "--done": `${(100 * done) / total}%` } as CSSProperties} />
        </span>
      )}
    </span>
  );
}
