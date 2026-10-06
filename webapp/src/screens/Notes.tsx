import { useId, type FocusEvent } from "react";
import { Link } from "wouter";
import { useDeleteNote, useNotes } from "../api/queries";
import type { Note } from "../api/types";
import { Fab } from "../components/Fab";
import { LinkedText, NoteProgress } from "../components/NoteBits";
import { PullToRefresh } from "../components/PullToRefresh";
import { SearchStatus } from "../components/SearchStatus";
import { SwipeRow } from "../components/SwipeRow";
import { Empty, ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { doneCount, MAX_NOTES } from "../lib/notes";
import { setNotesQuery, useNotesQuery } from "../lib/notesSearch";
import { fold, searchNotes } from "../lib/search";
import { confirmAction, haptic } from "../telegram";

/**
 * An address past the sixth line scrolls the clamped text when it takes the keyboard's focus. Once
 * the focus leaves the text, the card shows its first lines again.
 */
function backToTop(event: FocusEvent<HTMLParagraphElement>) {
  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
    event.currentTarget.scrollTop = 0;
  }
}

/**
 * A note in the list. The card opens the note by a link stretched over all of it, and each address
 * in the text is a button above that link: a tap on an address opens the address, not the note.
 * A checklist shows its title and how much of it is checked.
 */
function NoteCard({ note }: { note: Note }) {
  const textId = useId();
  const progressId = useId();
  const total = note.items.length;
  return (
    <div className="note-card">
      <Link
        href={`/notes/${note.id}`}
        className="note-card__open"
        aria-labelledby={total > 0 ? `${textId} ${progressId}` : textId}
      />
      <p className="note-card__text" id={textId} onBlur={backToTop}>
        {note.pinned && "📌 "}
        <LinkedText text={note.text} />
      </p>
      {total > 0 && (
        <span className="note-card__progress" id={progressId}>
          <NoteProgress done={doneCount(note.items)} total={total} bar />
        </span>
      )}
    </div>
  );
}

/**
 * The notes: the pinned ones on top, then the others, newest first — the server's order. A search
 * over them filters as it is typed and stays until the app closes.
 */
export function NotesScreen() {
  const t = useT();
  const notes = useNotes();
  const remove = useDeleteNote();
  const query = useNotesQuery();

  if (notes.isPending) return <Loader />;
  // A failed refresh keeps the list shown: only a first load that failed is an error.
  if (notes.isLoadingError) return <ErrorState onRetry={() => void notes.refetch()} />;

  const all = notes.data;
  const searching = fold(query) !== "";
  const shown = searchNotes(all, query);
  const pinned = shown.filter((note) => note.pinned);
  const others = shown.filter((note) => !note.pinned);

  const onDelete = async (id: number) => {
    if (await confirmAction(t.notes.confirmDelete)) remove.mutate(id);
  };
  const row = (note: Note) => (
    <SwipeRow key={note.id} onDelete={() => void onDelete(note.id)} deleteLabel={t.notes.delete}>
      <NoteCard note={note} />
    </SwipeRow>
  );
  // At the limit «+» stays where it is, dimmed, and says why instead of opening an editor that
  // could only be refused.
  const blocked = all.length >= MAX_NOTES
    ? () => {
      haptic("error");
      toast({ kind: "error", text: t.notes.limit(MAX_NOTES) });
    }
    : undefined;

  return (
    <>
      <PullToRefresh onRefresh={() => notes.refetch()}>
        <h1 className="screen__title">
          {t.tabs.notes} <span className="screen__count">{t.notes.counter(all.length, MAX_NOTES)}</span>
        </h1>
        {all.length === 0 ? (
          <Empty text={t.notes.empty} />
        ) : (
          <>
            <input
              type="search"
              className="input notes-search"
              placeholder={t.notes.search}
              aria-label={t.notes.search}
              enterKeyHint="search"
              value={query}
              onChange={(event) => setNotesQuery(event.target.value)}
              // The list is filtered already: Enter only puts the keyboard away.
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
              }}
            />
            <SearchStatus count={searching && shown.length > 0 ? t.notes.found(shown.length) : null}>
              {searching && shown.length === 0 && <Empty text={t.notes.nothingFound} />}
            </SearchStatus>
          </>
        )}
        {pinned.length > 0 && <h2 className="group__label">{t.notes.pinned}</h2>}
        {pinned.map(row)}
        {/* Without pinned notes above them, the others need no heading of their own. */}
        {pinned.length > 0 && others.length > 0 && <h2 className="group__label">{t.notes.others}</h2>}
        {others.map(row)}
      </PullToRefresh>
      {/* Outside the pull: a fixed button inside the moving body would move with it. */}
      <Fab href="/notes/new" label={t.notes.add} onBlocked={blocked} />
    </>
  );
}
