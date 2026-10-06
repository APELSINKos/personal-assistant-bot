import { useId, type ReactNode } from "react";
import { useT } from "../i18n";
import { codePoints } from "../lib/format";

export interface TextLimit {
  /** Longer than the limit: what the field is for waits until it is shorter. */
  over: boolean;
  /** Spread on the field: invalid while over, and described by the line under it. */
  field: { "aria-invalid": boolean; "aria-describedby": string | undefined };
  /** The line under the field: while over, its length against the limit. */
  hint: ReactNode;
}

/**
 * A field's text against its limit, in characters as the server counts them: code points, so an
 * emoji is one, where `length` and `maxLength` count it as two. Nothing stops the typing, and a
 * pasted text stays whole; while it is over the limit, the line under the field says by how
 * much. The line's region is in the page before the line comes, so a screen reader reads it out.
 */
export function useTextLimit(text: string, max: number): TextLimit {
  const t = useT();
  const id = useId();
  const length = codePoints(text);
  const over = length > max;
  return {
    over,
    field: { "aria-invalid": over, "aria-describedby": over ? id : undefined },
    hint: (
      <div aria-live="polite">
        {over && <p className="field__hint" id={id}>{t.notes.counter(length, max)}</p>}
      </div>
    ),
  };
}
