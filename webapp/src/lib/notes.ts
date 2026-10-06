import { words } from "./search";

// The limits of the notes, as the server keeps them (LIMITS in core/config.py). The app checks
// them before asking: a form that cannot be saved says why at once.
/** The characters of a note's text — of a checklist's title. */
export const MAX_TEXT = 500;
/** The notes of a user: at the last one «+» opens no new note. */
export const MAX_NOTES = 50;
/** The items of a checklist. */
export const MAX_ITEMS = 20;
/** The characters of an item. */
export const MAX_ITEM = 100;

/** Unicode's control characters (Cc): C0, DEL and C1 — a tab or a line break pasted into an item. */
function isControl(char: string): boolean {
  const code = char.charCodeAt(0);
  return code <= 0x1f || (code >= 0x7f && code <= 0x9f);
}

/**
 * An item as the server keeps it (notes.clean_item): one line, control characters as spaces, runs
 * of white space as one space, none at the ends. The app shows and measures an item so before it
 * goes, and its 100 characters are the server's.
 */
export function cleanItem(text: string): string {
  return words(Array.from(text, (char) => (isControl(char) ? " " : char)).join("")).join(" ");
}

/** A checklist's checked items: «✅ 2/5». */
export function doneCount(items: readonly { done: boolean }[]): number {
  return items.filter((item) => item.done).length;
}
