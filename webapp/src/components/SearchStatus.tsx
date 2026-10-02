import type { ReactNode } from "react";

/**
 * What a search came to, read out by a screen reader whenever it changes: how many results there
 * are (a count only the reader hears — the results themselves are on screen) or the notice shown
 * in their place. The region stays in the page while empty, so the reader is already listening
 * when the first answer comes.
 */
export function SearchStatus({ count, children }: { count: string | null; children?: ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      {count !== null && <span className="visually-hidden">{count}</span>}
      {children}
    </div>
  );
}
