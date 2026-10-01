import { createContext, useContext, type ReactNode } from "react";
import { en } from "./en";
import { ru, type Dict } from "./ru";

export type Lang = "ru" | "en";

const DICTS: Record<Lang, Dict> = { ru, en };
const RUSSIAN_FAMILY = new Set(["ru", "uk", "be", "kk"]);
const LangContext = createContext<Lang>("ru");

export function resolveLang(code?: string | null): Lang {
  const base = (code ?? "").toLowerCase().split("-")[0] ?? "";
  return RUSSIAN_FAMILY.has(base) ? "ru" : "en";
}

export function LangProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  return <LangContext.Provider value={lang}>{children}</LangContext.Provider>;
}

export function useLang(): Lang {
  return useContext(LangContext);
}

export function useT(): Dict {
  return DICTS[useLang()];
}

export function dict(lang: Lang): Dict {
  return DICTS[lang];
}

/**
 * The text that explains an error code. A code may be a string the server sent, so it counts only
 * when it is one of the dictionary's own keys, never a name every object has (`constructor`,
 * `__proto__`): those would give an empty text, or break rendering altogether.
 */
export function errorText(t: Dict, code: string | undefined): string {
  const messages: Record<string, string> = t.errors;
  const text = code !== undefined && Object.hasOwn(messages, code) ? messages[code] : undefined;
  return text ?? t.errors.generic;
}
