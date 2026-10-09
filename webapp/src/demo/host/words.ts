import type { Lang } from "../../i18n";

/** The host page's own words (spec §23.3); the app's stay in its dictionaries. */
export const WORDS: Record<Lang, { title: string; frame: string }> = {
  ru: { title: "Личный помощник — демо", frame: "Приложение «Личный помощник»" },
  en: { title: "Personal Assistant — demo", frame: "The Personal Assistant app" },
};
