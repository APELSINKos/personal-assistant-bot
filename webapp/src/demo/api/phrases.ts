/**
 * A phrase of a reminder (routers/reminders.py's parse, services/phrases.py), read by a subset of the
 * bot's rules (spec §5.4): the day (сегодня, завтра, послезавтра, «в среду», «в следующую пятницу»;
 * today, tomorrow, «on Wednesday», «next Friday»), the time («в 9», «в 9:30», «в 9.30», «19:45», «в 8
 * вечера», «в полдень»; «at 9:30», «7 pm», «at noon»), a time ahead («через 20 минут», «через 2 часа»,
 * «через 3 дня»; «in 20 minutes», «in 2 weeks») and the repeat (каждый день, по будням, по выходным,
 * «по средам», «каждый понедельник», раз в две недели, «каждый месяц 10-го»; every day, on weekdays, on
 * weekends, «every Monday», «every other Monday», «monthly on the 5th»), with «напомни» or «remind me»
 * before it. The bot's dates — «25 октября», «10.12» — are not in the subset: a phrase with one is not
 * understood rather than half understood. What is left of the words is the reminder's text. Words are
 * matched one by one: no pattern looks behind.
 */
import type { ParsedPhrase, RepeatName, RepeatRule } from "../../api/types";
import { addDaysIso, codePoints } from "../../lib/format";
import type { Visit } from "./data";
import { invalidInput, Problem } from "./http";
import { describeRule, firstMatchingDay, nextAfter, WEEKDAYS, WEEKENDS } from "./recurrence";
import { clockOf, localClock, localDay, MINUTE, momentOf, wall, weekdayOf } from "./time";

/** LIMITS.reminder_length. */
const TEXT_LENGTH = 200;

const RU_ACC = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"];
const RU_DAT = ["понедельникам", "вторникам", "средам", "четвергам", "пятницам", "субботам", "воскресеньям"];
const EN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
/** The months of a date, which the demo leaves to the bot. */
const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря",
  "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
  "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
];
/** phrases._NUMBERS: a number in words. */
const NUMBERS: Readonly<Record<string, number>> = {
  один: 1, одну: 1, одна: 1, два: 2, две: 2, три: 3, четыре: 4, пять: 5, шесть: 6, семь: 7, восемь: 8, девять: 9,
  десять: 10, пятнадцать: 15, двадцать: 20, тридцать: 30, сорок: 40, a: 1, an: 1, one: 1, two: 2, three: 3, four: 4,
  five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, fifteen: 15, twenty: 20, thirty: 30, forty: 40,
};
/** The units of a time ahead. */
const UNITS: Readonly<Record<string, "minute" | "hour" | "day" | "week">> = {
  минуту: "minute", минуты: "minute", минут: "minute", мин: "minute", minute: "minute", minutes: "minute",
  min: "minute", mins: "minute", час: "hour", часа: "hour", часов: "hour", hour: "hour", hours: "hour", hr: "hour",
  hrs: "hour", день: "day", дня: "day", дней: "day", day: "day", days: "day", неделю: "week", недели: "week",
  недель: "week", week: "week", weeks: "week",
};
/** «утром в 7» and «в 7 утром» read as «в 7 утра». */
const PART_OF_DAY: Readonly<Record<string, string>> = { утром: "утра", днем: "дня", вечером: "вечера", ночью: "ночи" };
const MERIDIEMS = ["утра", "дня", "вечера", "ночи", ...Object.keys(PART_OF_DAY)];
/**
 * phrases._UNITS: after the number of «в N» or «at N», a unit makes it a quantity, not a time — «в 2 раза», «в 5
 * минутах», «at 5 stars». A unit is a whole word with one of these endings, the word ending where the bot's \w ends,
 * so «в 7 метро» and «at 9 start» stay times and «в 20 км/ч» does not. A «%» needs nothing after it.
 */
const QUANTITY = new RegExp(String.raw`^(?:%|(?:${[
  "раза?", "км", "кг", "м", "г", "л", "мл", "см", "мм", "метр(?:а|е|у|ом|ов|ах|ами)?",
  "километр(?:а|е|у|ом|ов|ах|ами)?", "класс(?:а|е|у|ом|ы|ов|ах|ами)?", "лет", "год(?:а|у|ом|ы|ов|ах)?",
  "этаж(?:а|е|у|ом|и|ей|ах)?", "процент(?:а|ы|ом|ов|ах)?", "минутах", "часах", "шагах",
  "руб(?:ль|ля|лю|лем|лей|лях|лями)?", "times", "percent", "stars?", "km", "kg", "miles?", "years?", "floor",
].join("|")})(?![\p{L}\p{N}_]))`, "u");
/** The rules of a monthly repeat: «каждый месяц 10-го», «каждое 5 число», «on the 5th of every month». */
const NTH = /^\d{1,2}(?:-?го)?$/;
const ORDINAL = /^\d{1,2}(?:st|nd|rd|th)?$/;
const MONTHLY: readonly (readonly Test[])[] = [
  ["каждый", "месяц", NTH, "числа"], ["каждый", "месяц", NTH], ["ежемесячно", NTH, "числа"], ["ежемесячно", NTH],
  ["каждое", /^\d{1,2}(?:-?е)?$/, "число"], [NTH, "числа", "каждого", "месяца"], ["monthly", "on", "the", ORDINAL],
  ["every", "month", "on", "the", ORDINAL], ["on", "the", ORDINAL, "of", "every", "month"],
];
/** The words of a day from today. */
const DAYS: readonly (readonly [readonly Test[], number])[] = [
  [["на", "послезавтра"], 2], [["послезавтра"], 2], [["на", "завтра"], 1], [["завтра"], 1], [["на", "сегодня"], 0],
  [["сегодня"], 0], [["the", "day", "after", "tomorrow"], 2], [["day", "after", "tomorrow"], 2], [["tomorrow"], 1],
  [["today"], 0],
];

/** What a word must be: that word, one of these, or a pattern. */
type Test = string | readonly string[] | RegExp;

/** A word of the phrase: as written, as matched — lower case, «е» for «ё», no punctuation after it — and taken by a rule. */
interface Word {
  text: string;
  low: string;
  taken: boolean;
}

/** What a phrase says, and the words it leaves for the text. */
interface Parsed {
  text: string;
  time: string | null;
  /** A day from today: 0 today, 1 tomorrow. */
  days: number | null;
  /** A one-off on the next such weekday, 0 for Monday. */
  weekday: number | null;
  /** «через 20 минут»: a moment ahead. */
  delta: number | null;
  /** «через 3 дня»: a day ahead, its time apart. */
  deltaDays: number | null;
  repeat: RepeatName;
  weekdays: number | null;
  interval: number;
  monthDay: number | null;
}

/** A record's own entry: no word of a phrase reaches what every object inherits, such as «constructor». */
function own<T>(record: Readonly<Record<string, T>>, key: string): T | undefined {
  return Object.hasOwn(record, key) ? record[key] : undefined;
}

/** phrases._with_meridiem: «в 8 вечера» is 20, «в 12 ночи» 0, «7 pm» 19. */
function withMeridiem(hours: number, meridiem: string): number {
  const part = own(PART_OF_DAY, meridiem) ?? meridiem;
  if (part === "вечера" || part === "дня" || part === "pm") {
    if (hours >= 1 && hours <= 11) return hours + 12;
    return hours === 12 && part === "вечера" ? 0 : hours;
  }
  if (part === "утра" || part === "am") return hours === 12 ? 0 : hours;
  if (part === "ночи") return hours === 12 ? 0 : hours >= 6 && hours <= 11 ? hours + 12 : hours;
  return hours;
}

/** phrases._hhmm: «09:30», or null for what no clock shows. */
function hhmm(hours: number, minutes: number): string | null {
  if (hours > 23 || minutes > 59) return null;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

/** The phrase's words with the ones it understood taken out; null when it understood none, or has a date. */
function parse(phrase: string, todayWeekday: number): Parsed | null {
  const words: Word[] = phrase.split(/\s+/).filter(Boolean).map((text) => ({
    text, low: text.toLowerCase().replaceAll("ё", "е").replace(/[,.;:!?]+$/, ""), taken: false,
  }));
  /** A word not taken yet, as matched; "" for a taken one or past the end. */
  const low = (index: number) => {
    const word = words[index];
    return word && !word.taken ? word.low : "";
  };
  const fits = (index: number, test: Test) => {
    const word = low(index);
    if (!word) return false;
    if (typeof test === "string") return word === test;
    return test instanceof RegExp ? test.test(word) : test.includes(word);
  };
  const at = (start: number, tests: readonly Test[]) => tests.every((test, offset) => fits(start + offset, test));
  const take = (start: number, count: number) => {
    for (const word of words.slice(start, start + count)) word.taken = true;
  };
  /** The first place from the left where one of the runs stands: where, and which run. */
  const first = (runs: readonly (readonly Test[])[]): [number, number] | null => {
    for (let start = 0; start < words.length; start += 1) {
      const run = runs.findIndex((tests) => at(start, tests));
      if (run >= 0) return [start, run];
    }
    return null;
  };
  /** The first of the runs there, taken. */
  const named = (runs: readonly (readonly Test[])[]) => {
    const found = first(runs);
    if (found) take(found[0], runs[found[1]]?.length ?? 0);
    return found !== null;
  };
  /** The weekdays named from `start` — «вторникам и (по) четвергам», «monday, wednesday» — and the word after them. */
  const dayList = (start: number, day: (word: string) => number, joiner: string, again = "") => {
    if (day(low(start)) < 0) return null;
    let bits = 1 << day(low(start));
    let end = start + 1;
    for (;;) {
      let next = end;
      if (low(next) === joiner) next += 1;
      if (again && low(next) === again) next += 1;
      if (day(low(next)) < 0) return { bits, end };
      bits |= 1 << day(low(next));
      end = next + 1;
    }
  };
  /** The first `head` followed by weekdays, taken: their bits. */
  const headDays = (head: readonly Test[], day: (word: string) => number, joiner: string, again = "") => {
    for (let start = 0; start < words.length; start += 1) {
      const list = at(start, head) ? dayList(start + head.length, day, joiner, again) : null;
      if (!list) continue;
      take(start, list.end - start);
      return list.bits;
    }
    return null;
  };
  const ruAcc = (word: string) => RU_ACC.indexOf(word);
  const ruDat = (word: string) => RU_DAT.indexOf(word);
  const enDay = (word: string) => EN_DAYS.indexOf(word.replace(/s$/, ""));
  const enDays = (word: string) => (word.endsWith("s") ? EN_DAYS.indexOf(word.slice(0, -1)) : -1);
  const number = (index: number) => (/^\d{1,3}$/.test(low(index)) ? Number(low(index)) : own(NUMBERS, low(index)) ?? null);

  const parsed: Parsed = {
    text: "", time: null, days: null, weekday: null, delta: null, deltaDays: null, repeat: "none", weekdays: null,
    interval: 1, monthDay: null,
  };
  /** A rule that matched: what it says goes into the parse. */
  const set = (fields: Partial<Parsed>) => {
    Object.assign(parsed, fields);
    return true;
  };
  const weekly = (bits: number | null, interval = 1) => bits !== null && set({ repeat: "weekly", weekdays: bits, interval });

  // «Напомни (мне)», «remind me (to)», with «пожалуйста» or «please» before them: not the text.
  const polite = fits(0, ["please", "пожалуйста"]) ? 1 : 0;
  if (fits(polite, ["напомни", "напомнить"])) take(0, polite + (fits(polite + 1, "мне") ? 2 : 1));
  else if (at(polite, ["remind", "me"])) take(0, polite + (fits(polite + 2, "to") ? 3 : 2));

  // The repeat: the first of the bot's rules found in the phrase wins.
  const everyOtherWeek = () => {
    const found = first([["раз", "в", ["две", "2"], "недели"]]);
    if (!found) return false;
    const tail = found[0] + 4;
    take(found[0], 4);
    // On the days named right after it — «по вторникам и четвергам», «во вторник» — or on today's.
    const one = fits(tail, ["в", "во"]) ? ruAcc(low(tail + 1)) : -1;
    const days = fits(tail, "по") ? dayList(tail + 1, ruDat, "и", "по") : one >= 0 ? { bits: 1 << one, end: tail + 2 } : null;
    if (days) take(tail, days.end - tail);
    return weekly(days?.bits ?? 1 << todayWeekday, 2);
  };
  let refused = false;
  const monthly = () => {
    const found = first(MONTHLY);
    if (!found) return false;
    const length = MONTHLY[found[1]]?.length ?? 0;
    const day = Number(/\d+/.exec(words.slice(found[0], found[0] + length).map((word) => word.low).join(" "))?.[0]);
    // A day no month has: the phrase is not understood.
    if (day < 1 || day > 31) return (refused = true);
    take(found[0], length);
    return set({ repeat: "monthly", monthDay: day });
  };
  [
    () => named([["каждый", "день"], ["ежедневно"], ["every", "day"], ["everyday"], ["daily"]]) && set({ repeat: "daily" }),
    () => named([
      ["по", "будням"], ["в", "будни"], ["по", "рабочим", "дням"], ["каждый", "будний", "день"], ["on", "weekdays"],
      ["weekdays"], ["every", "weekday"],
    ]) && weekly(WEEKDAYS),
    () => named([["по", "выходным"], ["в", "выходные"], ["on", "weekends"], ["weekends"], ["every", "weekend"]])
      && weekly(WEEKENDS),
    everyOtherWeek,
    () => weekly(headDays([/^кажд(?:ый|ую|ое)$/, /^втор(?:ой|ую|ое)$/], ruAcc, "и"), 2),
    () => weekly(headDays(["every", "other"], enDay, "and"), 2),
    () => weekly(headDays([/^кажд(?:ый|ую|ое)$/], ruAcc, "и")),
    () => weekly(headDays(["по"], ruDat, "и", "по")),
    () => weekly(headDays(["every"], enDay, "and")),
    () => weekly(headDays(["on"], enDays, "and")),
    monthly,
  ].some((rule) => rule());
  if (refused) return null;

  // A time ahead; a repeat has no single moment, so its «через …» stays in its text.
  for (let start = 0; parsed.repeat === "none" && start < words.length; start += 1) {
    if (!fits(start, ["через", "in"])) continue;
    let minutes: number | null = null;
    let end = start + 1;
    if (fits(end, "полчаса")) [minutes, end] = [30, end + 1];
    else if (at(end, ["half", "an", "hour"])) [minutes, end] = [30, end + 3];
    else if (at(end, ["полтора", "часа"])) [minutes, end] = [90, end + 2];
    else {
      const count = number(end);
      if (count !== null) end += 1;
      const unit = own(UNITS, low(end));
      if (!unit) continue;
      end += 1;
      if (unit === "day" || unit === "week") parsed.deltaDays = (count ?? 1) * (unit === "week" ? 7 : 1);
      else minutes = (count ?? 1) * (unit === "hour" ? 60 : 1);
      // «через 1 час 30 минут», «in 2 hours and 15 minutes».
      const joined = fits(end, ["и", "and"]) ? 1 : 0;
      const more = unit === "hour" ? number(end + joined) : null;
      if (minutes !== null && more !== null && own(UNITS, low(end + joined + 1)) === "minute") {
        [minutes, end] = [minutes + more, end + joined + 2];
      }
    }
    if (minutes !== null) parsed.delta = minutes * MINUTE;
    take(start, end - start);
    break;
  }

  // The bot's dates are not in the subset: «25 октября», «October 25», «10.12», «25.10.2026».
  const dated = words.some((_, index) => {
    if ((ORDINAL.test(low(index)) && MONTHS.includes(low(index + 1)))
      || (MONTHS.includes(low(index)) && ORDINAL.test(low(index + 1)))) return true;
    const numeric = /^(\d{1,2})\.(\d{2})(\.(?:\d{2}|\d{4}))?$/.exec(low(index));
    const [day, month] = [Number(numeric?.[1]), Number(numeric?.[2])];
    if (!numeric || day < 1 || day > 31 || month < 1 || month > 12) return false;
    // Without a year «в 10.12» is a time.
    return numeric[3] !== undefined || !["в", "во", "к"].includes(low(index - 1));
  });
  if (dated) return null;

  const day = first(DAYS.map(([run]) => run));
  if (day) {
    const [run, shift] = DAYS[day[1]] ?? [[], 0];
    take(day[0], run.length);
    parsed.days = shift;
  }

  // A one-off weekday: «в среду», «в следующую пятницу», «on Wednesday», «next friday».
  for (let start = 0; parsed.days === null && parsed.repeat === "none" && start < words.length; start += 1) {
    const russian = fits(start, ["в", "во", "на"]);
    let end = russian || fits(start, "on") ? start + 1 : start;
    const next = fits(end, russian ? /^следующ(?:ий|ую|ее)$/ : "next");
    if (next || fits(end, russian ? /^эт(?:от|у|о)$/ : "this")) end += 1;
    const index = russian ? ruAcc(low(end)) : EN_DAYS.indexOf(low(end));
    if (index < 0) continue;
    take(start, end + 1 - start);
    if (next) parsed.days = 7 - todayWeekday + index;
    else parsed.weekday = index;
    break;
  }

  // The time, the bot's way and order: «в полдень», then «at 9:30 pm», «в 8 вечера», «19:45».
  const noon = first([[["в", "at"], ["полдень", "полночь", "noon", "midnight"]]]);
  /** A unit right after the number makes it a quantity; past a comma or a full stop it does not: «в 10, м. Тверская». */
  const quantity = (number: number) => /\d$/.test(words[number]?.text ?? "") && QUANTITY.test(low(number + 1));
  const clocks: ((start: number) => [string | null, number] | null)[] = [
    // «at 9», «at 9.30 pm», «7pm», «7:30 am».
    (start) => {
      const after = fits(start, "at") ? start + 1 : start;
      const glued = /^(\d{1,2})(?::(\d{2}))?([ap])\.?m\.?$/.exec(low(after));
      if (glued) return [hhmm(withMeridiem(Number(glued[1]), `${glued[3]}m`), Number(glued[2] ?? 0)), after + 1];
      const clock = (after > start ? /^(\d{1,2})(?:[:.](\d{2}))?$/ : /^(\d{1,2})(?::(\d{2}))?$/).exec(low(after));
      const meridiem = /^([ap])\.?m\.?$/.exec(low(after + 1));
      if (clock && meridiem) return [hhmm(withMeridiem(Number(clock[1]), `${meridiem[1]}m`), Number(clock[2] ?? 0)), after + 2];
      if (!clock || after === start || quantity(after)) return null;
      return [hhmm(Number(clock[1]), Number(clock[2] ?? 0)), after + 1];
    },
    // «в 9», «в 9.30», «к 9», «в 9 часов», «утром в 7», «в 8 вечера».
    (start) => {
      const pre = own(PART_OF_DAY, low(start)) ? 1 : 0;
      const clock = fits(start + pre, ["в", "во", "к"]) ? /^(\d{1,2})(?:[:.](\d{2}))?$/.exec(low(start + pre + 1)) : null;
      if (!clock || quantity(start + pre + 1)) return null;
      let end = start + pre + 2;
      if (fits(end, ["ч", "час", "часа", "часов"])) end += 1;
      const meridiem = fits(end, MERIDIEMS) ? low(end) : pre ? low(start) : "";
      if (fits(end, MERIDIEMS)) end += 1;
      return [hhmm(withMeridiem(Number(clock[1]), meridiem), Number(clock[2] ?? 0)), end];
    },
    // «19:45».
    (start) => {
      const clock = /^(\d{1,2}):(\d{2})$/.exec(low(start));
      return clock ? [hhmm(Number(clock[1]), Number(clock[2])), start + 1] : null;
    },
  ];
  if (noon) {
    parsed.time = ["полдень", "noon"].includes(low(noon[0] + 1)) ? "12:00" : "00:00";
    take(noon[0], 2);
  } else {
    for (const clock of clocks) {
      // The first match of a way counts; a time no clock shows sends the search to the next way.
      const start = words.findIndex((_, index) => clock(index) !== null);
      const [time, end] = (start >= 0 ? clock(start) : null) ?? [null, 0];
      if (time === null) continue;
      parsed.time = time;
      take(start, end - start);
      break;
    }
  }

  const when = [parsed.delta, parsed.deltaDays, parsed.days, parsed.weekday, parsed.time];
  if (parsed.repeat === "none" && when.every((part) => part === null)) return null;
  // What is left, without the commas around it, or a «please» or a «to» before it.
  const trim = (text: string) => text.replace(/^[\s,.;:—–-]+|[\s,.;:—–-]+$/g, "");
  parsed.text = trim(
    trim(words.filter((word) => !word.taken).map((word) => word.text).join(" "))
      .replace(/^(?:please|пожалуйста)(?![\p{L}\p{N}_])[\s,]*/iu, "")
      .replace(/^(?:что(?:бы)?|о\s+том,?\s+что(?:бы)?|to|that)(?![\p{L}\p{N}_])\s*/u, ""),
  );
  return parsed;
}

/** POST /reminders/parse: what the form fills in from a phrase, as the router answers. */
export function parsePhrase(visit: Visit, phrase: string): ParsedPhrase {
  const now = visit.now();
  const zone = visit.zone();
  const today = localDay(zone, now);
  const parsed = parse(phrase, weekdayOf(today));
  if (!parsed) throw invalidInput({ field: "text", reason: "phrase_not_understood" });
  const text = parsed.text.trim();
  // No text left is fine: the form keeps its own text field. Only too long is refused.
  if (codePoints(text) > TEXT_LENGTH) throw invalidInput({ field: "text", reason: "length", limit: TEXT_LENGTH });
  let date: string | null = null;
  let time = parsed.time;
  let rule: RepeatRule | null = null;
  if (parsed.repeat !== "none") {
    // A repeat with its time: from its first firing on; every other week counts from its first day.
    if (parsed.time !== null) {
      const weekly: RepeatRule = {
        repeat: parsed.repeat, time_local: parsed.time, weekdays: parsed.weekdays, interval_weeks: parsed.interval,
        month_day: parsed.monthDay, anchor_date: today,
      };
      const first = parsed.interval === 2 ? firstMatchingDay(weekly, today, `${today}T${clockOf(wall(zone, now))}`) : today;
      rule = first === null ? null : { ...weekly, anchor_date: first };
      try {
        date = rule && localDay(zone, nextAfter(rule, now, zone));
      } catch (error) {
        // _first_day: a rule that never fires has no first day to show.
        if (!(error instanceof Problem)) throw error;
      }
    }
  } else if (parsed.delta !== null) {
    // A moment ahead: its day and its time, to the minute.
    date = localDay(zone, now + parsed.delta);
    time = localClock(zone, now + parsed.delta);
  } else if (parsed.deltaDays !== null || parsed.days !== null) {
    date = addDaysIso(today, parsed.deltaDays ?? parsed.days ?? 0);
  } else {
    // A weekday or a time alone: the next one still ahead — noon finds the day when no time is named.
    const ahead = parsed.weekday === null ? 0 : (parsed.weekday - weekdayOf(today) + 7) % 7;
    const day = addDaysIso(today, ahead);
    date = momentOf(zone, day, parsed.time ?? "12:00") > now ? day : addDaysIso(day, parsed.weekday === null ? 1 : 7);
  }
  return {
    text, repeat: parsed.repeat, date, time, weekdays: parsed.weekdays, interval_weeks: parsed.interval,
    month_day: parsed.monthDay, description: rule && describeRule(rule, visit.lang()),
  };
}
