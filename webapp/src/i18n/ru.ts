import type { HabitColor, MoneyKind, StreakUnit } from "../api/types";
import type { ShownChance } from "../lib/format";

const rules = new Intl.PluralRules("ru");

function plural(n: number, one: string, few: string, many: string): string {
  const form = rules.select(n);
  if (form === "one") return one;
  return form === "few" ? few : many;
}

/** «12 дней» or «5 недель». */
function streakIn(count: number, unit: StreakUnit): string {
  return `${count} ${unit === "days" ? plural(count, "день", "дня", "дней") : plural(count, "неделя", "недели", "недель")}`;
}

/** A budget warning's parts, each already formatted (lib/money.ts, alertText). */
export interface AlertWords {
  threshold: number;
  percent: number;
  /** «☕ Кафе»; null for the budget of all expenses. */
  name: string | null;
  month: string;
  spent: string;
  budget: string;
}

/** A budget's line, each amount already formatted (lib/money.ts, budgetText). */
export interface BudgetWords {
  budget: string;
  /** What is left, or what is overspent when `over`. */
  rest: string;
  over: boolean;
  /** What is left for each day to the month's end; null for a past month or a category. */
  perDay: string | null;
}

/** A rate's days, each value already formatted (lib/money.ts, historyWords). */
export interface HistoryWords {
  first: string;
  last: string;
  change: string;
  percent: string;
  low: string;
  high: string;
}

export const ru = {
  tabs: {
    today: "Сегодня",
    calendar: "Календарь",
    habits: "Привычки",
    notes: "Заметки",
    money: "Деньги",
    more: "Ещё",
  },
  common: {
    save: "Сохранить",
    retry: "Повторить",
    loading: "Загрузка…",
    searching: "Ищу…",
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
    bestStreak: (name: string, count: number, unit: StreakUnit) =>
      `🔥 Лучшая серия: «${name}» — ${streakIn(count, unit)}`,
    notes: (count: number) => `${count} ${plural(count, "заметка", "заметки", "заметок")}`,
    pull: "Потяни, чтобы обновить",
    refreshing: "Обновляю…",
    lessons: "Пары",
    lessonsOver: "Пары закончились",
    tomorrow: (emoji: string, range: string) => `Завтра: ${emoji} ${range}`,
    // Every weather text takes its `chance` from shownChance (lib/format.ts): null leaves it unsaid.
    // A line of «Сегодня» may wrap: the drop stays with its number, as the percent sign does.
    withChance: (text: string, chance: ShownChance | null) =>
      chance === null ? text : `${text}, 💧\u00a0${chance}\u00a0%`,
    classes: (start: string, startWeather: string, end: string, endWeather: string) =>
      `🎓 На пары (${start}): ${startWeather} · после пар (${end}): ${endWeather}`,
    classesAfter: (end: string, endWeather: string) => `🎓 После пар (${end}): ${endWeather}`,
    allNotes: (count: number) => `Все заметки (${count})`,
  },
  weather: {
    title: "Погода",
    now: "Сейчас",
    feels: (temp: string) => `Ощущается как ${temp}`,
    wind: (speed: string, gusts: string | null) =>
      gusts === null ? `Ветер ${speed} м/с` : `Ветер ${speed} м/с, порывы до ${gusts} м/с`,
    humidity: (percent: number) => `Влажность ${percent}\u00a0%`,
    hours: "24 часа",
    days: "7 дней",
    chart: (min: string, max: string) => `Температура на сутки: от ${min} до ${max}`,
    stripLabel: "Прогноз на 24 часа",
    // `chance` and `percent`: from shownChance, as in today.withChance.
    hourLabel: (time: string, description: string, temp: string, chance: ShownChance | null) =>
      `${time}, ${description}, ${temp}${chance === null ? "" : `, осадки ${chance}\u00a0%`}`,
    dayLabel: (day: string, description: string, min: string, max: string, chance: ShownChance | null) =>
      `${day}: ${description}, от ${min} до ${max}${chance === null ? "" : `, осадки ${chance}\u00a0%`}`,
    chance: (percent: ShownChance | null) =>
      percent === null ? "" : `💧 ${percent}\u00a0%`,
    sun: (sunrise: string, sunset: string) => `🌅 ${sunrise} · 🌇 ${sunset}`,
    polarNight: "🌑 Полярная ночь",
    polarDay: "☀️ Полярный день",
    cityGone: "Этого города уже нет в списке",
    unavailable: "Погода временно недоступна",
    share: "Поделиться прогнозом",
    cardSent: "Картинка в чате с ботом — перешли её, куда захочешь",
    writeText: "Без разрешения бот не сможет прислать картинку.",
  },
  calendar: {
    title: "Календарь",
    showMonth: "Показать месяц",
    hideMonth: "Скрыть месяц",
    today: "↩ Сегодня",
    prevWeek: "Предыдущая неделя",
    nextWeek: "Следующая неделя",
    empty: "Ничего не запланировано",
    count: (n: number) => `${n} ${plural(n, "напоминание", "напоминания", "напоминаний")}`,
    words: { today: "Сегодня", tomorrow: "Завтра", afterTomorrow: "Послезавтра", yesterday: "Вчера" },
    add: "Добавить напоминание",
    delete: "Удалить напоминание",
    confirmDelete: "Удалить напоминание?",
    confirmDeleteSeries: (text: string) => `Удалить повтор «${text}» целиком?`,
    lessons: (n: number) => `${n} ${plural(n, "пара", "пары", "пар")}`,
  },
  reminderForm: {
    newTitle: "Новое напоминание",
    editTitle: "Напоминание",
    phrase: "Напиши, например: завтра в 9 купить молоко",
    understand: "Понять",
    text: "О чём напомнить",
    date: "Дата",
    time: "Время",
    repeat: "Повтор",
    repeats: {
      none: "Не повторять", daily: "Каждый день", weekdays: "По будням", weekends: "По выходным",
      days: "Дни недели", biweekly: "Раз в 2 недели", monthly: "Каждый месяц",
    },
    weekdays: ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    monthDay: "Число месяца",
    firstDate: "Первый раз",
    saved: "Напомню!",
    confirmDiscard: "Выйти без сохранения?",
    writeTitle: "Разрешить боту писать?",
    writeText: "Без разрешения бот не сможет прислать напоминание.",
    openChat: "Открыть чат с ботом",
  },
  habits: {
    empty: "Привычек пока нет. Нажми «+», чтобы начать.",
    progress: (done: number, total: number) =>
      `${done} из ${total} ${plural(total, "дня", "дней", "дней")}`,
    newTitle: "Новая привычка",
    name: "Название",
    confirmDelete: (name: string) => `Удалить привычку «${name}» вместе со всей статистикой?`,
    toggle: (name: string, state: string) => `${name}: ${state}. Нажми, чтобы изменить`,
    state: { done: "выполнено", skipped: "пропущено", none: "без отметки" },
    add: "Добавить привычку",
    streakIn,
    week: (done: number, goal: number) => `${done} из ${goal} на этой неделе`,
    goalDaily: "Каждый день",
    goalWeekly: (count: number) => `${count} ${plural(count, "раз", "раза", "раз")} в неделю`,
    since: (date: string) => `с ${date}`,
    record: "Рекорд",
    year: "За год",
    yearMap: "Последние 12 месяцев",
    dayToggle: (date: string, state: string) => `${date}: ${state}. Нажми, чтобы изменить`,
    share: "Поделиться",
    cardSent: "Карточка в чате с ботом — перешли её, куда захочешь",
    writeText: "Без разрешения бот не сможет прислать карточку.",
    edit: "Изменить",
    editTitle: "Привычка",
    emoji: "Эмодзи",
    color: "Цвет",
    colors: {
      mint: "мятный",
      sky: "голубой",
      violet: "фиолетовый",
      rose: "розовый",
      coral: "коралловый",
      amber: "янтарный",
      sand: "песочный",
      slate: "серый",
    } satisfies Record<HabitColor, string>,
    goal: "Цель",
    goalHint: "Серия и проценты пересчитаются по новой цели.",
    prevMonth: "Предыдущий месяц",
    nextMonth: "Следующий месяц",
    streakTitle: "Серия",
    months: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    pickWeek: (range: string) => `Показать месяц недели ${range}`,
    gone: "Этой привычки уже нет.",
    toHabits: "К привычкам",
    deleteButton: "Удалить привычку",
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
    search: "Найти в заметках",
    nothingFound: "Ничего не нашлось",
    found: (count: number) => `Найдено заметок: ${count}`,
    pinned: "Закреплённые",
    others: "Остальные",
    limit: (limit: number) => `Достигнут лимит — ${limit} заметок. Удали лишние.`,
    items: "Пункты",
    newItem: "Новый пункт",
    addItem: "Добавить",
    clearDone: "Убрать отмеченные",
    removeItem: (text: string) => `Удалить пункт «${text}»`,
    pin: "Закрепить",
    unpin: "Открепить",
    itemsLimit: (limit: number) => `Не больше ${limit} пунктов`,
    needTitle: "Напиши название списка",
    progress: (done: number, total: number) => `✅ ${done}/${total}`,
    // What a screen reader says for `progress`.
    progressLabel: (done: number, total: number) => `Отмечено ${done} из ${total}`,
    gone: "Этого уже нет",
    links: "Ссылки",
  },
  money: {
    alert: ({ threshold, percent, name, month, spent, budget }: AlertWords) => {
      const which = name === null ? "" : ` «${name}»`;
      return threshold >= 100
        ? `🚨 Бюджет${which} на ${month} закончился: ${spent} из ${budget}`
        : `⚠️ Потрачено ${percent}\u00a0% бюджета${which} на ${month}: ${spent} из ${budget}`;
    },
    prevMonth: "Предыдущий месяц",
    nextMonth: "Следующий месяц",
    spent: "Потрачено",
    budget: ({ budget, rest, over, perDay }: BudgetWords) =>
      over
        ? `из ${budget} · перерасход ${rest}`
        : `из ${budget} · осталось ${rest}${perDay === null ? "" : `, по ${perDay} в день`}`,
    income: (income: string, balance: string) => `Доходы ${income} · баланс ${balance}`,
    byCategory: "По категориям",
    byDay: "По дням",
    ring: (total: string, shares: string) => `Траты за месяц ${total}: ${shares}`,
    entriesWord: (count: number) => plural(count, "запись", "записи", "записей"),
    days: (day: string, amount: string) => `Траты по дням; больше всего — ${day}: ${amount}`,
    entries: "Записи",
    empty: "В этом месяце записей нет.",
    emptyCategory: "В этой категории в этом месяце записей нет.",
    showAll: (name: string) => `Показать все записи, не только «${name}»`,
    deleteEntry: "Удалить запись",
    deleteRow: (title: string, amount: string) => `Удалить запись «${title}», ${amount}`,
    add: "Добавить запись",
    newEntry: "Новая запись",
    editEntry: "Запись",
    amount: "Сумма",
    amountHint: "Сумма — число больше нуля, не больше двух знаков после запятой",
    kind: "Расход или доход",
    kinds: { expense: "Расход", income: "Доход" } satisfies Record<MoneyKind, string>,
    category: "Категория",
    note: "Заметка",
    notePlaceholder: "Необязательно",
    day: "День",
    prevDay: "Предыдущий день",
    nextDay: "Следующий день",
    dayHint: "День — не позже сегодняшнего и не раньше, чем год назад",
    confirmDelete: "Удалить запись?",
    gone: "Этой записи уже нет.",
    toMoney: "К деньгам",
    setBudget: "Задать бюджет",
    budgetLink: "🎯 Бюджет",
    categoriesLink: "🗂 Категории",
    budgetTitle: "Бюджет на месяц",
    budgetHint: "Пустое поле — без бюджета. Предупрежу, когда потратишь 80\u00a0% и 100\u00a0%; бюджет действует каждый месяц.",
    budgetTotal: "Общий",
    budgetCategories: "По категориям",
    noBudget: "Нет",
    categoriesTitle: "Категории",
    kindsPlural: { expense: "Расходы", income: "Доходы" } satisfies Record<MoneyKind, string>,
    hiddenMark: "скрыта",
    newCategory: "Новая категория",
    categoriesFull: (limit: number) => `Категорий уже ${limit} — новую не добавить. Ненужную можно переименовать.`,
    categoryTitle: "Категория",
    name: "Название",
    emoji: "Эмодзи",
    hide: "Скрыть категорию",
    hideHint: "Скрытая категория не предлагается при записи, а её записи остаются в итогах.",
    otherFixed: "«Другое» скрыть нельзя: сюда попадает всё, чему не нашлось категории.",
    categoryGone: "Этой категории нет.",
    toCategories: "К категориям",
    rates: "Курсы ЦБ",
    ratesOn: (date: string) => `На ${date}`,
    ratesUnavailable: "Курсы ЦБ сейчас недоступны",
    currency: "Валюта",
    chart: (name: string) => `Курс: ${name}, за 30 дней`,
    history: ({ first, last, change, percent, low, high }: HistoryWords) =>
      `За 30 дней: с ${first} до ${last} (${change}, ${percent}); минимум ${low}, максимум ${high}`,
    historyUnavailable: "Истории курса сейчас нет",
    converter: "Конвертер",
    from: "Из",
    to: "В",
    swap: "Поменять валюты местами",
  },
  more: {
    noCities: "Ничего не нашлось",
    citiesFound: (n: number) => `Найдено городов: ${n}`,
    morning: "Утренняя сводка",
    morningTime: "Время сводки",
    language: "Язык",
    auto: "Авто",
    languageNames: { ru: "Русский", en: "English" },
    about: "О приложении",
    version: (value: string) => `Версия ${value}`,
    source: "Исходный код на GitHub",
    currency: "Валюта",
    currencyHint: "Суммы уже сделанных записей не пересчитываются — меняется только знак.",
    cities: "Города",
    homeHint: "по его времени приходят напоминания и сводка",
    changeHome: "Сменить домашний",
    addCity: "Добавить город",
    newHome: "Новый домашний город",
    cityToAdd: "Какой город добавить",
    citiesLimit: "До 5 городов вместе с домашним",
    deleteCity: (name: string) => `Удалить город «${name}»`,
    confirmDeleteCity: (name: string) => `Удалить город «${name}»?`,
    data: "Данные",
    // The licence's name does not break across lines, and no line starts with a dash: each dash
    // keeps the word before it.
    credits: "Погода\u00a0— open-meteo.com, названия городов\u00a0— geonames.org; лицензия CC\u00a0BY\u00a04.0 (creativecommons.org/licenses/by/4.0), приложение округляет данные и добавляет советы.",
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
    phrase_not_understood: "Не нашёл, когда напомнить — например, «завтра в 9»",
    repeat_invalid: "Выбери хотя бы один день",
    needs_time: "Укажи время",
    schedule: "Укажи дату и время или повтор",
    length: "Слишком длинный текст — сократи",
    forbidden_host: "Нужна ссылка https:// или webcal:// на календарь в интернете",
    unreachable: "Не получилось скачать календарь — проверь ссылку или попробуй позже",
    too_large: "Календарь слишком большой или сложный — разобрать его не получится",
    not_calendar: "Это не похоже на календарь .ics",
    source: "Выбери группу, ссылку или файл",
    limit_pinned_note: "Закрепить можно не больше 5 заметок — открепи одну",
    limit_note_item: "В заметке уже 20 пунктов",
    limit_city: "Уже 5 городов вместе с домашним — удали лишний",
    duplicate_city: "Этот город уже в списке",
    write_forbidden: "Бот пока не может тебе написать — открой чат с ботом и нажми «Запустить»",
    share_failed: "Не получилось отправить картинку — попробуй ещё раз или выбери другой чат",
    weather_unavailable: "Погода временно недоступна",
  },
  schedule: {
    title: "Расписание",
    entry: "Расписание пар",
    notConnected: "Не подключено",
    intro: "Подключи расписание — пары появятся в календаре, «Сегодня», «Моём дне» и утренней сводке.",
    group: "Группа МИРЭА",
    groupPlaceholder: "Например, ИКБО-63-24",
    noGroups: "Такой группы нет в справочнике",
    groupsFound: (n: number) => `Найдено групп: ${n}`,
    building: "Справочник групп ещё не готов — если твоей группы нет, попробуй позже или подключи расписание по ссылке.",
    link: "Ссылка на календарь",
    linkPlaceholder: "webcal://… или https://…",
    connect: "Подключить",
    connected: "Расписание подключено",
    file: "Файл .ics",
    fileHint: "Файл не обновляется сам — при изменениях загрузи новый.",
    pickFile: "Выбрать файл",
    cancel: "Отмена",
    kinds: { mirea: "Группа МИРЭА", url: "По ссылке", file: "Файл .ics" },
    untitled: "Календарь без названия",
    updated: (when: string) => `Обновлено ${when}`,
    stale: (when: string) => `Данные от ${when} — источник пока недоступен`,
    failed: "Последнее обновление не удалось",
    ahead: (n: number) => `Впереди ${n} ${plural(n, "пара", "пары", "пар")}`,
    empty: "В календаре нет занятий на ближайшие месяцы",
    refresh: "Обновить",
    refreshed: "Расписание обновлено",
    change: "Сменить источник",
    disconnect: "Отключить",
    confirmDisconnect: "Отключить расписание? Пары пропадут из календаря и «Моего дня».",
    alerts: "Напоминать о парах",
    alertOff: "Выкл",
    alertMinutes: (minutes: number) => `${minutes} мин`,
  },
  auth: {
    title: "Открой приложение заново",
    expired: "Сессия устарела. Закрой приложение и открой его снова из чата с ботом.",
    outside: "Это приложение работает внутри Telegram. Открой его из чата с ботом.",
  },
};

export type Dict = typeof ru;
