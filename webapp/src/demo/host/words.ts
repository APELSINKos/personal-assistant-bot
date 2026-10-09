import type { Lang } from "../../i18n";

/** The host page's own words (spec §23.3); the app's stay in its dictionaries. */
export interface HostWords {
  title: string;
  kicker: string;
  /** The bot's name, in the header and over the pitch. */
  name: string;
  /** The README's line about the bot. */
  tagline: string;
  tryIt: string;
  /** Where the pitch's links take the phone. */
  tries: { habit: string; expense: string; phrase: string; weather: string; shopping: string };
  language: string;
  theme: string;
  dark: string;
  light: string;
  startOver: string;
  /** What the demo's data are, and its clock. */
  data: string;
  /** The line a phone shows for a while on every load. */
  hint: string;
  menu: string;
  about: string;
  aboutText: string;
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
    kicker: "Демо · приложение внутри Telegram",
    name: "Личный помощник",
    tagline:
      "Telegram-бот, который не просто скажет «+12°C», а напишет «🌧 Через 40 минут дождь — возьми зонт». "
      + "Погода, напоминания, расписание пар, заметки, привычки и деньги — в чате и в приложении прямо внутри "
      + "Telegram, а по утрам бот пишет первым.",
    tryIt: "Попробовать:",
    tries: {
      habit: "Отметить привычку",
      expense: "Записать трату",
      phrase: "Напоминание фразой",
      weather: "Погода на неделю",
      shopping: "Список покупок",
    },
    language: "Язык:",
    theme: "Тема:",
    dark: "тёмная",
    light: "светлая",
    startOver: "Начать заново",
    data:
      "Данные выдуманные и живут только в этой вкладке: ничего не сохраняется и никуда не отправляется. "
      + "Время — московское. Telegram и сервер не нужны.",
    hint: "Это демо: данные выдуманные, ничего не сохраняется, время московское",
    menu: "Меню демо",
    about: "Об этом демо",
    aboutText:
      "Это то же приложение, что открывается в Telegram, без единой правки: вместо сервера ему отвечают "
      + "выдуманные данные прямо в этой странице.",
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
    kicker: "Demo · an app inside Telegram",
    name: "Personal Assistant",
    tagline:
      "A Telegram bot that doesn't just say “+12°C” — it says “🌧 Rain in 40 min — take an umbrella”. "
      + "Weather, reminders, class schedule, notes, habits and money — in the chat and in an app right inside "
      + "Telegram, and in the morning the bot writes first.",
    tryIt: "Try:",
    tries: {
      habit: "Mark a habit",
      expense: "Add an expense",
      phrase: "A reminder in plain words",
      weather: "The week's weather",
      shopping: "Shopping list",
    },
    language: "Language:",
    theme: "Theme:",
    dark: "dark",
    light: "light",
    startOver: "Start over",
    data:
      "The data are made up and live only in this tab: nothing is saved or sent anywhere. "
      + "The clock shows Moscow time. No Telegram or server needed.",
    hint: "This is a demo: the data are made up, nothing is saved, the clock shows Moscow time",
    menu: "Demo menu",
    about: "About this demo",
    aboutText:
      "It's the same app that opens in Telegram, unchanged: instead of a server, made-up data answer it "
      + "right in this page.",
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
