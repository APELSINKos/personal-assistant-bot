import type { Lang } from "../../i18n";

/**
 * The demo's made-up visitor and their home, in the visitor's language (spec §5.3), and the title of
 * their pinned shopping list (§23.4): the host page's «Список покупок» opens the list by it.
 */
export const WORDS: Record<Lang, { name: string; home: string; shopping: string }> = {
  ru: { name: "Саша", home: "Москва", shopping: "Покупки" },
  en: { name: "Alex", home: "Moscow", shopping: "Shopping" },
};
