import { Link } from "wouter";
import { useDeleteNote, useNotes } from "../api/queries";
import { Fab } from "../components/Fab";
import { Empty, ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useT } from "../i18n";
import { confirmAction } from "../telegram";

export function NotesScreen() {
  const t = useT();
  const notes = useNotes();
  const remove = useDeleteNote();

  if (notes.isPending) return <Loader />;
  if (notes.isError) return <ErrorState onRetry={() => void notes.refetch()} />;

  const onDelete = async (id: number) => {
    if (await confirmAction(t.notes.confirmDelete)) remove.mutate(id);
  };

  return (
    <>
      <h1 className="screen__title">{t.tabs.notes}</h1>
      {notes.data.length === 0 && <Empty text={t.notes.empty} />}
      {notes.data.map((note) => (
        <SwipeRow key={note.id} onDelete={() => void onDelete(note.id)} deleteLabel={t.notes.delete}>
          <Link href={`/notes/${note.id}`} className="note-card">
            <span className="note-card__text">{note.text}</span>
          </Link>
        </SwipeRow>
      ))}
      <Fab href="/notes/new" label={t.notes.add} />
    </>
  );
}
