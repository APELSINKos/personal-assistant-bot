import { Fragment, type CSSProperties } from "react";
import { creditParts, type TextPart } from "../lib/links";
import { openLink } from "../telegram";

/**
 * A plain part of the line in three: what touches the link before it (the «),» after a link),
 * its own words, and what touches the link after it (the «(» before one). A part with no space
 * in it, between two links, goes whole to the first of them.
 */
function plainPart(parts: TextPart[], place: number) {
  const text = parts[place]?.text ?? "";
  const toPrevious = parts[place - 1]?.url ? (/^\S*/u.exec(text)?.[0] ?? "") : "";
  const rest = text.slice(toPrevious.length);
  const toNext = parts[place + 1]?.url ? (/\S*$/u.exec(rest)?.[0] ?? "") : "";
  return { toPrevious, own: rest.slice(0, rest.length - toNext.length), toNext };
}

/**
 * Where the data on screen come from, each source it names a link: the licence of Open-Meteo and
 * GeoNames (CC BY 4.0) asks for them next to the data. `index` times its entrance with the cards'.
 * A link keeps the punctuation it touches on its own line: a bracket left at the end of a line,
 * or a comma starting the next one, would read as a slip.
 */
export function Credit({ text, index = 0, className = "" }: { text: string; index?: number; className?: string }) {
  const parts = creditParts(text);
  return (
    <p className={`credit ${className}`.trim()} style={{ "--i": index } as CSSProperties}>
      {parts.map((part, place) => {
        const url = part.url;
        if (url === null) return <Fragment key={place}>{plainPart(parts, place).own}</Fragment>;
        return (
          <span key={place} className="credit__piece">
            {parts[place - 1]?.url === null && plainPart(parts, place - 1).toNext}
            <button type="button" className="credit__link" onClick={() => openLink(url)}>
              {part.text}
            </button>
            {parts[place + 1]?.url === null && plainPart(parts, place + 1).toPrevious}
          </span>
        );
      })}
    </p>
  );
}
