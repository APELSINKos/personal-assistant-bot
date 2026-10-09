import type { ReactNode } from "react";
import { errorCode } from "../api/queries";
import { errorText, useT } from "../i18n";

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

/**
 * What a search says before it has an answer: «Ищу…» while one is on the way (a service that
 * hangs keeps it there for seconds), then why it failed, in the refusal's own words.
 */
export function SearchProgress({
  search,
}: { search: { data: unknown; isFetching: boolean; isError: boolean; error: unknown } }) {
  const t = useT();
  if (search.data !== undefined) return null;
  if (search.isFetching) return <p className="muted">{t.common.searching}</p>;
  if (search.isError) return <p className="muted">{errorText(t, errorCode(search.error))}</p>;
  return null;
}
