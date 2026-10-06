import { Fragment, type CSSProperties } from "react";
import { creditParts } from "../lib/links";
import { openLink } from "../telegram";

/**
 * Where the data on screen come from, each source it names a link: the licence of Open-Meteo and
 * GeoNames (CC BY 4.0) asks for them next to the data. `index` times its entrance with the cards'.
 */
export function Credit({ text, index = 0, className = "" }: { text: string; index?: number; className?: string }) {
  return (
    <p className={`credit ${className}`.trim()} style={{ "--i": index } as CSSProperties}>
      {creditParts(text).map((part, place) => {
        const url = part.url;
        if (url === null) return <Fragment key={place}>{part.text}</Fragment>;
        return (
          <button key={place} type="button" className="credit__link" onClick={() => openLink(url)}>
            {part.text}
          </button>
        );
      })}
    </p>
  );
}
