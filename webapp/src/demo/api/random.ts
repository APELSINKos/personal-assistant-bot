/**
 * The demo's chance (spec §5.2): numbers drawn from a hash of what they are for — a date, the
 * language, the kind of data — so a day keeps its marks and spendings from one visit to the next, a
 * new day brings its own, and the same `?at=` gives the same data on every load. FNV-1a makes the
 * seed of the parts, mulberry32 the numbers.
 */

/** FNV-1a, 32 bits, over the text's UTF-16 units. */
export function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** mulberry32: numbers in [0, 1) from a 32-bit seed. */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The numbers of one thing: «2026-10-07», "ru", "money" draw the same ones every time. */
export function draws(...parts: (string | number)[]): () => number {
  return mulberry32(fnv1a(parts.join("|")));
}

/** One number of one thing, in [0, 1). */
export function chance(...parts: (string | number)[]): number {
  return draws(...parts)();
}
