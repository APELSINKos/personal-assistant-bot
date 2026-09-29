const rules = new Intl.PluralRules("ru");

function plural(n: number, one: string, few: string, many: string): string {
  const form = rules.select(n);
  if (form === "one") return one;
  return form === "few" ? few : many;
}

export const ru = {
  tabs: {
    today: "Сегодня",
    reminders: "Напоминания",
    habits: "Привычки",
    notes: "Заметки",
    more: "Ещё",
  },
  common: {
    save: "Сохранить",
    retry: "Повторить",
    loading: "Загрузка…",
    add: "Добавить",
    saved: "Сохранено",
    sections: "Разделы",
    dev: "Режим разработки",
  },
  today: {
    weatherUnavailable: "Погода временно недоступна",
    feelsLike: (value: string) => `ощущается как ${value}`,
    plans: "Сегодня",
    freeDay: "Свободный день",
    habits: (done: number, total: number) => `Привычки · ${done} из ${total}`,
    noHabits: "Привычек пока нет — добавь первую во вкладке «Привычки»",
    bestStreak: (name: string, days: number) =>
      `🔥 Лучшая серия: «${name}» — ${days} ${plural(days, "день", "дня", "дней")}`,
    notes: (count: number) => `${count} ${plural(count, "заметка", "заметки", "заметок")}`,
    pull: "Потяни, чтобы обновить",
    refreshing: "Обновляю…",
  },
  reminders: {
    empty: "Напоминаний нет. Нажми «+», чтобы добавить.",
    today: "Сегодня",
    tomorrow: "Завтра",
    newTitle: "Новое напоминание",
    text: "О чём напомнить",
    date: "Дата",
    time: "Время",
    confirmDelete: "Удалить напоминание?",
    delete: "Удалить напоминание",
    add: "Добавить напоминание",
    saved: "Напомню!",
  },
  habits: {
    empty: "Привычек пока нет. Нажми «+», чтобы начать.",
    streak: (days: number) => `${days} ${plural(days, "день", "дня", "дней")}`,
    progress: (done: number, total: number) =>
      `${done} из ${total} ${plural(total, "дня", "дней", "дней")}`,
    newTitle: "Новая привычка",
    name: "Название",
    confirmDelete: (name: string) => `Удалить привычку «${name}» вместе со всей статистикой?`,
    toggle: (name: string, state: string) => `${name}: ${state}. Нажми, чтобы изменить`,
    state: { done: "выполнено", skipped: "пропущено", none: "без отметки" },
    delete: (name: string) => `Удалить привычку «${name}»`,
    add: "Добавить привычку",
  },
  notes: {
    empty: "Заметок пока нет. Нажми «+», чтобы создать первую.",
    newTitle: "Новая заметка",
    editTitle: "Заметка",
    placeholder: "Текст заметки",
    counter: (length: number, max: number) => `${length}/${max}`,
    confirmDiscard: "Выйти без сохранения?",
    confirmDelete: "Удалить заметку?",
    delete: "Удалить заметку",
    add: "Добавить заметку",
  },
  more: {
    city: "Город",
    searchCity: "Найти город",
    noCities: "Ничего не нашлось",
    morning: "Утренняя сводка",
    morningTime: "Время сводки",
    language: "Язык",
    auto: "Авто",
    languageNames: { ru: "Русский", en: "English" },
    about: "О приложении",
    version: (value: string) => `Версия ${value}`,
    source: "Исходный код на GitHub",
  },
  errors: {
    generic: "Что-то пошло не так. Попробуй ещё раз.",
    not_found: "Этого уже нет",
    limit_reached: "Достигнут лимит — удали что-нибудь лишнее",
    past: "Это время уже прошло",
    duplicate: "Такая уже есть",
    validation_error: "Проверь, что всё заполнено правильно",
    upstream_unavailable: "Сервис временно недоступен",
    rate_limited: "Слишком много запросов — подожди минуту",
    network: "Нет связи с сервером",
  },
  auth: {
    title: "Открой приложение заново",
    expired: "Сессия устарела. Закрой приложение и открой его снова из чата с ботом.",
    outside: "Это приложение работает внутри Telegram. Открой его из чата с ботом.",
  },
};

export type Dict = typeof ru;
