import type { Lang } from "../../i18n";

/** The demo's made-up visitor and their home, in the visitor's language (spec §5.3). */
export const WORDS: Record<Lang, { name: string; home: string }> = {
  ru: { name: "Саша", home: "Москва" },
  en: { name: "Alex", home: "Moscow" },
};
