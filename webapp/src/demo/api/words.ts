import type { Lang } from "../../i18n";
import type { Preset } from "./data";

/**
 * The demo's made-up visitor and their home, in the visitor's language (spec §5.3), and the title of
 * their pinned shopping list (§23.4): the host page's «Список покупок» opens the list by it.
 */
export const WORDS: Record<Lang, { name: string; home: string; shopping: string }> = {
  ru: { name: "Саша", home: "Москва", shopping: "Покупки" },
  en: { name: "Alex", home: "Moscow", shopping: "Shopping" },
};

/** The weather's words of a WMO code (wmo-* of the bot's locales). */
export type WeatherWord =
  | "clear" | "partly" | "cloudy" | "fog" | "drizzle" | "rain" | "snow" | "showers" | "snowfall" | "storm" | "unknown";

/** What the server says in the user's language: the bot's own words, as its locales have them. */
export interface Texts {
  weather: Record<WeatherWord, string>;
  /** tip-*: snow for rain at 0 °C and below. */
  tips: {
    now: (snow: boolean) => string;
    soon: (snow: boolean, minutes: number) => string;
    later: (snow: boolean, hour: string) => string;
    warmer: string;
    colder: string;
    wind: string;
    frost: string;
    heat: string;
    bike: string;
    calm: string;
  };
  /** repeat-*: how a repeat is described. */
  repeat: {
    daily: (time: string) => string;
    weekdays: (time: string) => string;
    weekends: (time: string) => string;
    weekly: (days: string, time: string) => string;
    biweekly: (days: string, time: string) => string;
    monthly: (day: number, time: string) => string;
  };
  /** Babel's abbreviated weekdays, Monday first. */
  days: readonly string[];
  /** money-cat-*: the presets' names. */
  presets: Record<Preset, string>;
}

/** «минуту», «минуты», «минут»: Fluent's one, few and many of Russian. */
function russianPlural(count: number, one: string, few: string, many: string): string {
  if (count % 10 === 1 && count % 100 !== 11) return one;
  return count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 12 || count % 100 > 14) ? few : many;
}

export const TEXTS: Record<Lang, Texts> = {
  ru: {
    weather: {
      clear: "ясно", partly: "малооблачно", cloudy: "пасмурно", fog: "туман", drizzle: "морось", rain: "дождь",
      snow: "снег", showers: "ливень", snowfall: "снегопад", storm: "гроза", unknown: "нет данных",
    },
    tips: {
      now: (snow) => (snow ? "🌨 Сейчас идёт снег — надень капюшон" : "🌧 Сейчас идёт дождь — возьми зонт"),
      soon: (snow, minutes) => {
        const unit = russianPlural(minutes, "минуту", "минуты", "минут");
        return snow
          ? `🌨 Через ${minutes} ${unit} снег — надень капюшон`
          : `🌧 Через ${minutes} ${unit} дождь — возьми зонт`;
      },
      later: (snow, hour) =>
        snow
          ? `🌨 Снег ожидается после ${hour} — капюшон сегодня пригодится`
          : `☔ Дождь ожидается после ${hour} — зонт сегодня пригодится`,
      warmer: "🧥 Утром холодно, вечером потеплеет",
      colder: "🌡 К вечеру похолодает — захвати кофту",
      wind: "💨 Сильный ветер — одевайся плотнее",
      frost: "🥶 Очень холодно — одевайся теплее",
      heat: "🥵 Жара — пей больше воды",
      bike: "🚲 Сегодня хороший день для велосипеда",
      calm: "👌 Погода без сюрпризов",
    },
    repeat: {
      daily: (time) => `каждый день в ${time}`,
      weekdays: (time) => `по будням в ${time}`,
      weekends: (time) => `по выходным в ${time}`,
      weekly: (days, time) => `${days} в ${time}`,
      biweekly: (days, time) => `раз в 2 недели: ${days} в ${time}`,
      monthly: (day, time) => `каждый месяц ${day}-го в ${time}`,
    },
    days: ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    presets: {
      groceries: "Продукты", cafe: "Кафе", transport: "Транспорт", home: "Дом", phone: "Связь", health: "Здоровье",
      clothes: "Одежда", fun: "Развлечения", study: "Учёба", gifts: "Подарки", subscriptions: "Подписки",
      other: "Другое", salary: "Зарплата", stipend: "Стипендия", gifts_in: "Подарили", other_in: "Другое",
    },
  },
  en: {
    weather: {
      clear: "clear", partly: "partly cloudy", cloudy: "overcast", fog: "fog", drizzle: "drizzle", rain: "rain",
      snow: "snow", showers: "showers", snowfall: "heavy snow", storm: "thunderstorm", unknown: "no data",
    },
    tips: {
      now: (snow) => (snow ? "🌨 It's snowing now — put your hood on" : "🌧 It's raining now — take an umbrella"),
      soon: (snow, minutes) =>
        snow ? `🌨 Snow in ${minutes} min — put your hood on` : `🌧 Rain in ${minutes} min — take an umbrella`,
      later: (snow, hour) =>
        snow
          ? `🌨 Snow expected after ${hour} — a hood will come in handy`
          : `☔ Rain expected after ${hour} — an umbrella will come in handy`,
      warmer: "🧥 Cold in the morning, warmer in the evening",
      colder: "🌡 It gets colder by the evening — take a sweater",
      wind: "💨 Strong wind — dress warmly",
      frost: "🥶 Very cold — wrap up",
      heat: "🥵 It's hot — drink more water",
      bike: "🚲 A great day for a bike ride",
      calm: "👌 No weather surprises today",
    },
    repeat: {
      daily: (time) => `every day at ${time}`,
      weekdays: (time) => `on weekdays at ${time}`,
      weekends: (time) => `on weekends at ${time}`,
      weekly: (days, time) => `${days} at ${time}`,
      biweekly: (days, time) => `every other week: ${days} at ${time}`,
      monthly: (day, time) => `monthly on day ${day} at ${time}`,
    },
    days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    presets: {
      groceries: "Groceries", cafe: "Eating out", transport: "Transport", home: "Home", phone: "Phone & internet",
      health: "Health", clothes: "Clothes", fun: "Fun", study: "Study", gifts: "Gifts", subscriptions: "Subscriptions",
      other: "Other", salary: "Salary", stipend: "Stipend", gifts_in: "Gifts received", other_in: "Other",
    },
  },
};

/** The texts of the demo's records, in the language it was opened in (spec §23.4). */
export interface SeedWords {
  /** The timetable's week label: «5 неделя», as MIREA's calendar names its weeks. */
  week: (number: number) => string;
  group: string;
  /** The eight notes; the shopping list's title is WORDS.shopping, which the host page looks for. */
  notes: {
    shoppingItems: readonly string[];
    packing: string;
    packingItems: readonly string[];
    door: string;
    gifts: string;
    reading: string;
    pancakes: string;
    coursework: string;
    debt: string;
  };
  reminders: {
    parcel: string; call: string; lab: string; dentist: string; water: string; workout: string; plants: string;
    phone: string;
  };
  habits: { sport: string; reading: string; swimming: string; sugar: string };
  /** Monday to Sunday: the start, the end, the title, the kind and the room of each lesson. */
  lessons: readonly (readonly [number, string, string, string, string | null, string])[];
  /** The notes of the money entries. */
  money: {
    coffee: string; lunch: string; groceries: string; metro: string; taxi: string; phone: string;
    subscription: string; cinema: string; pharmacy: string; clothes: string; stipend: string; job: string;
  };
}

export const SEED_WORDS: Record<Lang, SeedWords> = {
  ru: {
    week: (number) => `${number} неделя`,
    group: "ДЕМО-01-26",
    notes: {
      shoppingItems: ["молоко", "хлеб", "яйца", "сыр", "яблоки", "кофе", "макароны"],
      packing: "Собрать в поездку",
      packingItems: ["паспорт", "зарядка", "наушники", "зонт", "свитер", "зубная щётка", "книга", "билеты"],
      door: "Код домофона: 45В7",
      gifts: "Идеи подарков: маме — плед, брату — настольная игра, бабушке — фотоальбом",
      reading: "Почитать осенью: что-нибудь о космосе, сборник рассказов, книгу о дизайне интерфейсов",
      pancakes: "Блины: 2 яйца, 500 мл молока, 200 г муки, щепотка соли, ложка сахара",
      coursework: "Курсовая: план до 20 октября, источники — https://example.com/library",
      debt: "Вернуть Диме 1 500 ₽ до пятницы",
    },
    reminders: {
      parcel: "Забрать посылку", call: "Созвон по курсовой", lab: "Сдать лабораторную",
      dentist: "Записаться к стоматологу", water: "Выпить воды", workout: "Зарядка", plants: "Полить цветы",
      phone: "Оплатить телефон",
    },
    habits: { sport: "Спорт", reading: "Читать 20 страниц", swimming: "Бассейн", sugar: "Без сахара" },
    lessons: [
      [0, "09:00", "10:30", "Физика", "ЛК", "А-212"],
      [0, "10:40", "12:10", "Программирование на Python", "ПР", "И-212"],
      [1, "10:40", "12:10", "Теория вероятностей", "ЛК", "А-118"],
      [1, "12:40", "14:10", "Английский язык", "ПР", "Г-304"],
      [2, "10:40", "12:10", "Математический анализ", "ЛК", "А-16"],
      [2, "12:40", "14:10", "Разработка баз данных", "ПР", "И-212-б"],
      [3, "09:00", "10:30", "Физика", "ЛАБ", "Б-105"],
      [3, "10:40", "12:10", "Разработка баз данных", "ЛК", "А-118"],
      [4, "12:40", "14:10", "Теория вероятностей", "ПР", "Г-307"],
      [4, "14:20", "15:50", "Физкультура", "ПР", "спортзал"],
      [5, "10:40", "12:10", "Программирование на Python", "ПР", "И-212"],
      [6, "12:00", "13:00", "Консультация: Математический анализ", null, "А-16"],
    ],
    money: {
      coffee: "кофе", lunch: "обед", groceries: "продукты", metro: "метро", taxi: "такси", phone: "связь",
      subscription: "подписка", cinema: "кино", pharmacy: "аптека", clothes: "одежда", stipend: "стипендия",
      job: "подработка",
    },
  },
  en: {
    week: (number) => `Week ${number}`,
    group: "DEMO-01-26",
    notes: {
      shoppingItems: ["milk", "bread", "eggs", "cheese", "apples", "coffee", "pasta"],
      packing: "Packing list",
      packingItems: ["passport", "charger", "earphones", "umbrella", "sweater", "toothbrush", "book", "tickets"],
      door: "Door code: 45B7",
      gifts: "Gift ideas: a blanket for Mum, a board game for my brother, a photo album for Grandma",
      reading: "To read this autumn: something about space, a short story collection, a book on interface design",
      pancakes: "Pancakes: 2 eggs, 500 ml of milk, 200 g of flour, a pinch of salt, a spoonful of sugar",
      coursework: "Coursework: the outline by October 20, sources — https://example.com/library",
      debt: "Pay Dima back 1,500 ₽ by Friday",
    },
    reminders: {
      parcel: "Pick up the parcel", call: "Coursework call", lab: "Hand in the lab report",
      dentist: "Book a dentist appointment", water: "Drink water", workout: "Workout", plants: "Water the plants",
      phone: "Pay the phone bill",
    },
    habits: { sport: "Sport", reading: "Read 20 pages", swimming: "Swimming", sugar: "No sugar" },
    lessons: [
      [0, "09:00", "10:30", "Physics", null, "A-212"],
      [0, "10:40", "12:10", "Python Programming", null, "I-212"],
      [1, "10:40", "12:10", "Probability Theory", null, "A-118"],
      [1, "12:40", "14:10", "English", null, "G-304"],
      [2, "10:40", "12:10", "Calculus", null, "A-16"],
      [2, "12:40", "14:10", "Databases", null, "I-212-b"],
      [3, "09:00", "10:30", "Physics lab", null, "B-105"],
      [3, "10:40", "12:10", "Databases", null, "A-118"],
      [4, "12:40", "14:10", "Probability Theory", null, "G-307"],
      [4, "14:20", "15:50", "Physical education", null, "gym"],
      [5, "10:40", "12:10", "Python Programming", null, "I-212"],
      [6, "12:00", "13:00", "Consultation: Calculus", null, "A-16"],
    ],
    money: {
      coffee: "coffee", lunch: "lunch", groceries: "groceries", metro: "metro", taxi: "taxi", phone: "phone",
      subscription: "subscription", cinema: "cinema", pharmacy: "pharmacy", clothes: "clothes", stipend: "stipend",
      job: "part-time job",
    },
  },
};
