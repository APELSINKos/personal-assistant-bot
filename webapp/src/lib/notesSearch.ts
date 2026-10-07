import { useSyncExternalStore } from "react";

/**
 * What the notes are searched for, kept in memory until the Mini App closes: the query outlives
 * a visit to a note and back. Not in the address — under the hash router a «?q=» would land
 * outside the hash and stay there after the next screens.
 */
let query = "";
const listeners = new Set<() => void>();

export function getNotesQuery(): string {
  return query;
}

export function setNotesQuery(value: string): void {
  if (value === query) return;
  query = value;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useNotesQuery(): string {
  return useSyncExternalStore(subscribe, getNotesQuery);
}
