import { openLink, openTelegramLink } from "../telegram";

/** The bot's chat: where "Start" gives the bot permission to write. */
export const BOT_CHAT_URL = "https://t.me/ikbo63_24_bot";

// The weather's source, the city names' and their licence: CC BY 4.0 asks for them to be named,
// as «Ещё» → «Данные» does.
export const OPEN_METEO_URL = "https://open-meteo.com/";
export const GEONAMES_URL = "https://www.geonames.org/";
export const LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/";

/**
 * An address in a note: http://…, https://… or t.me/…, up to white space, an angle bracket, a
 * guillemet or a double quote. No lookbehind: older iOS WebViews do not know it.
 */
const ADDRESS = /\b(?:https?:\/\/|t\.me\/)[^\s<>«»"“”„]+/giu;
// What ends the sentence an address stands in: «см. https://x.ru.» opens https://x.ru.
const TRAILING = new Set([".", ",", ";", ":", "!", "?", "'", "’", "…"]);
const SCHEME = /^https?:\/\//i;
// The hosts openTelegramLink takes (telegram-web-app.js throws on any other).
const TELEGRAM_HOSTS = new Set(["t.me", "telegram.me"]);

// What a credit line names as bare hosts, and what each opens.
const CREDIT = /open-meteo\.com|geonames\.org|creativecommons\.org\/licenses\/by\/4\.0/g;
const CREDITS = new Map([
  ["open-meteo.com", OPEN_METEO_URL],
  ["geonames.org", GEONAMES_URL],
  ["creativecommons.org/licenses/by/4.0", LICENCE_URL],
]);

export interface Link {
  /** As the text has it. */
  text: string;
  /** What a tap opens. */
  url: string;
}

/** A piece of a text: plain words (`url` null) or an address. */
export type TextPart = Link | { text: string; url: null };

/** The text cut into plain parts and the links `link` makes of the matches of `pattern`. */
function cut(text: string, pattern: RegExp, link: (found: string) => Link | null): TextPart[] {
  const parts: TextPart[] = [];
  let from = 0;
  for (const match of text.matchAll(pattern)) {
    const found = link(match[0]);
    if (found === null) continue;
    if (match.index > from) parts.push({ text: text.slice(from, match.index), url: null });
    parts.push(found);
    from = match.index + found.text.length;
  }
  if (from < text.length) parts.push({ text: text.slice(from), url: null });
  return parts;
}

function count(text: string, char: string): number {
  return text.split(char).length - 1;
}

/** An address without the punctuation of the text around it. */
function trimmed(found: string): string {
  let address = found;
  for (;;) {
    const last = address.slice(-1);
    if (TRAILING.has(last)) address = address.slice(0, -1);
    // «(https://x.ru/a)»: the bracket is the text's; «…/wiki/Мир_(значения)» keeps its own.
    else if (last === ")" && count(address, "(") < count(address, ")")) address = address.slice(0, -1);
    else return address;
  }
}

function addressLink(found: string): Link | null {
  const text = trimmed(found);
  const url = SCHEME.test(text) ? text : `https://${text}`;
  try {
    return new URL(url).hostname ? { text, url } : null;
  } catch {
    return null; // «https://» and nothing a browser could open after it
  }
}

/** The text in plain parts and addresses, in order: a note shows each address as a button. */
export function linkParts(text: string): TextPart[] {
  return cut(text, ADDRESS, addressLink);
}

/** The addresses of a text, each once, in order: the editor lists them under its field. */
export function findLinks(text: string): Link[] {
  const links: Link[] = [];
  for (const part of linkParts(text)) {
    if (part.url !== null && !links.some((link) => link.url === part.url)) links.push(part);
  }
  return links;
}

/**
 * A credit line (`more.credits`) with each source it names as a link: the line writes them as
 * bare hosts, which are no addresses for a note.
 */
export function creditParts(text: string): TextPart[] {
  return cut(text, CREDIT, (found) => {
    const url = CREDITS.get(found);
    return url === undefined ? null : { text: found, url };
  });
}

function isTelegramLink(url: string): boolean {
  try {
    return TELEGRAM_HOSTS.has(new URL(url).hostname);
  } catch {
    return false;
  }
}

/** Opens an address: a t.me one inside Telegram, any other in the browser. */
export function openAddress(url: string): void {
  if (isTelegramLink(url)) openTelegramLink(url);
  else openLink(url);
}
