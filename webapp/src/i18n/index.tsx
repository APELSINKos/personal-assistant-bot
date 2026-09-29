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
