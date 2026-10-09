import type { Lang } from "../../i18n";

/** The host page's own words (spec §23.3); the app's stay in its dictionaries. */
export interface HostWords {
  title: string;
  /** The bot's name, in the header. */
  name: string;
  /** Under the name: what this is. */
  demo: string;
  close: string;
  back: string;
  cancel: string;
  ok: string;
  closing: string;
  closeAnyway: string;
  closed: string;
  openAgain: string;
  bot: string;
  source: string;
  writeAccess: string;
  allow: string;
  shareTitle: string;
  example: string;
  send: string;
  sample: { habit: string; forecast: string };
  sent: string;
  loading: string;
  /** The app's frame, for screen readers. */
  frame: string;
}

export const WORDS: Record<Lang, HostWords> = {
  ru: {
    title: "Личный помощник — демо",
    name: "Личный помощник",
    demo: "демо",
    close: "Закрыть",
    back: "Назад",
    cancel: "Отмена",
    ok: "OK",
    closing: "Изменения могут не сохраниться.",
    closeAnyway: "Всё равно закрыть",
    closed: "Приложение закрыто",
    openAgain: "Открыть снова",
    bot: "Открыть бота в Telegram",
    source: "Исходный код на GitHub",
    writeAccess: "Разрешить боту «Личный помощник» присылать сообщения?",
    allow: "Разрешить",
    shareTitle: "В Telegram здесь откроется выбор чата",
    example: "пример",
    send: "Отправить",
    sample: { habit: "Пример: карточка привычки", forecast: "Пример: прогноз на неделю" },
    sent: "Это демо — ничего не отправлено",
    loading: "Приложение загружается",
    frame: "Приложение «Личный помощник»",
  },
  en: {
    title: "Personal Assistant — demo",
    name: "Personal Assistant",
    demo: "demo",
    close: "Close",
    back: "Back",
    cancel: "Cancel",
    ok: "OK",
    closing: "Changes may not be saved.",
    closeAnyway: "Close anyway",
    closed: "The app is closed",
    openAgain: "Open again",
    bot: "Open the bot in Telegram",
    source: "Source code on GitHub",
    writeAccess: "Allow “Personal Assistant” to send you messages?",
    allow: "Allow",
    shareTitle: "In Telegram, the chat picker opens here",
    example: "example",
    send: "Send",
    sample: { habit: "Example: a habit card", forecast: "Example: the week's forecast" },
    sent: "This is a demo — nothing was sent",
    loading: "The app is loading",
    frame: "The Personal Assistant app",
  },
};

/** The bot's chat and the project's code: where the page's two links lead. */
export const LINKS = {
  bot: "https://t.me/ikbo63_24_bot",
  source: "https://github.com/APELSINKos/personal-assistant-bot",
} as const;
