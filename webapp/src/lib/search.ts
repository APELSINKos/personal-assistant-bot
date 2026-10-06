/**
 * White space as Python's str.split() takes it: notes.fold on the server splits with that, and a
 * query must fall into the same words on both sides. JavaScript's \s would take U+FEFF as well and
 * leave out U+001C–U+001F and U+0085.
 */
const SPACE = new Set(
  [
    0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
    0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
  ].map((code) => String.fromCharCode(code)),
);

/** The words of a text, split at white space as Python's str.split() splits. */
export function words(text: string): string[] {
  const found: string[] = [];
  let word = "";
  for (const char of text) {
    if (!SPACE.has(char)) {
      word += char;
    } else if (word) {
      found.push(word);
      word = "";
    }
  }
  if (word) found.push(word);
  return found;
}

/**
 * A text as the search compares it, the same as notes.fold in the bot (searchCases.json holds the
 * cases both sides are tested with): lower case, «ё» as «е», runs of white space as one space and
 * none at the ends. Lower case, not case folding: JavaScript has none, and it would turn «ß» into
 * «ss» and «ς» into «σ» where toLowerCase and Python's lower() keep them.
 */
export function fold(text: string): string {
  return words(text.toLowerCase().replaceAll("ё", "е")).join(" ");
}

/** A note as the search reads it: a checklist is searched by its items too. */
export interface Searchable {
  text: string;
  items: readonly { text: string }[];
}

function holds(note: Searchable, wanted: readonly string[]): boolean {
  // A word is found within the text or within one item, never across the two.
  const haystack = [note.text, ...note.items.map((item) => item.text)].map(fold).join("\n");
  return wanted.every((word) => haystack.includes(word));
}

/** Whether a note holds every word of the query, each anywhere, part of a word too. */
export function matches(note: Searchable, query: string): boolean {
  return holds(note, words(fold(query)));
}

/** The notes that hold every word of the query, in their order; all of them for an empty query. */
export function searchNotes<T extends Searchable>(notes: readonly T[], query: string): T[] {
  const wanted = words(fold(query));
  return notes.filter((note) => holds(note, wanted));
}
