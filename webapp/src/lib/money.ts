import type { CategoryTotal, MoneyAlert, MoneyEntry } from "../api/types";
import type { Lang } from "../i18n";
import type { Dict } from "../i18n/ru";
import { daysBetween, parseIsoDate } from "./format";

/** Joins the parts of an amount, so a line never breaks inside one. */
export const NBSP = "\u00a0";

export const DEFAULT_CURRENCY = "RUB";

/** The most an entry or a budget may be, in hundredths: a billion (LIMITS.amount_max). */
export const AMOUNT_MAX = 100_000_000_000;

interface Currency {
  sign: string;
  /** In English the sign goes before the number: «$1,200». */
  before?: true;
}

/**
 * The currencies a user can keep accounts in, in the settings' order — the same as the server's
 * (assistant/core/money_style.py; tests/unit/test_money_style.py compares the two).
 */
export const CURRENCIES: Record<string, Currency> = {
  RUB: { sign: "₽" },
  USD: { sign: "$", before: true },
  EUR: { sign: "€", before: true },
  KZT: { sign: "₸" },
  BYN: { sign: "Br" },
  UAH: { sign: "₴" },
  UZS: { sign: "сўм" },
  KGS: { sign: "сом" },
  AMD: { sign: "֏" },
  GEL: { sign: "₾" },
  AZN: { sign: "₼" },
  TJS: { sign: "смн" },
  TRY: { sign: "₺" },
  CNY: { sign: "¥" },
  GBP: { sign: "£", before: true },
  PLN: { sign: "zł" },
};

/** The emoji a category can have — the server's set, which the bot's report can draw. */
export const CATEGORY_EMOJI = [
  "🛒", "☕", "🍔", "🍕", "🍺", "🚌", "🚕", "🚇",
  "⛽", "🚗", "🚲", "🏠", "💡", "🔧", "📱", "💻",
  "💊", "🏥", "🦷", "💇", "👕", "👟", "👶", "🐕",
  "🎮", "🎬", "🎵", "🎨", "📚", "🎓", "🎁", "🎀",
  "🧸", "📺", "💼", "💰", "🏦", "💳", "🧾", "📦",
] as const;

export function currencySign(code: string): string {
  return CURRENCIES[code]?.sign ?? code;
}

/**
 * «1 200 ₽», «430,50 ₽»; in English «$1,200» and «1,200 ₽». Kopecks only when there are some;
 * `plus` marks an income: «+5 000 ₽». The same as the bot's (money_phrases.format_amount).
 */
export function formatAmount(hundredths: number, currency: string, lang: Lang, plus = false): string {
  const digits = hundredths % 100 === 0 ? 0 : 2;
  const number = new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    .format(hundredths / 100)
    .replace(/\s/g, NBSP);
  const style = CURRENCIES[currency];
  const text = style?.before && lang === "en"
    ? `${style.sign}${number}`
    : `${number}${NBSP}${currencySign(currency)}`;
  return plus ? `+${text}` : text;
}

/** A balance: «+12 600 ₽», «−3 000 ₽». */
export function formatSigned(hundredths: number, currency: string, lang: Lang): string {
  const text = formatAmount(Math.abs(hundredths), currency, lang);
  return hundredths >= 0 ? `+${text}` : `−${text}`;
}

/**
 * What the user typed into an amount field, as the API takes it: «1 200,5» → «1200.50». Null for
 * anything else: letters, a sign, three decimals, zero, more than a billion.
 */
export function parseAmount(text: string): string | null {
  const match = /^(\d{1,10})(?:[.,](\d{1,2}))?$/.exec(text.replace(/\s/g, ""));
  if (!match) return null;
  const whole = (match[1] ?? "").replace(/^0+(?=\d)/, "");
  const cents = match[2]?.padEnd(2, "0");
  const hundredths = Number(whole) * 100 + Number(cents ?? 0);
  if (hundredths <= 0 || hundredths > AMOUNT_MAX) return null;
  return cents === undefined ? whole : `${whole}.${cents}`;
}

/** An amount back in its field, without groups: «1200», «430,50» («430.50» in English). */
export function amountText(hundredths: number, lang: Lang): string {
  const whole = Math.floor(hundredths / 100);
  const cents = hundredths % 100;
  if (!cents) return String(whole);
  return `${whole}${lang === "ru" ? "," : "."}${String(cents).padStart(2, "0")}`;
}

/** «2026-10» for a day of October 2026. */
export function monthOf(iso: string): string {
  return iso.slice(0, 7);
}

/** The month `delta` months away: «2026-12» + 1 is «2027-01». */
export function addMonths(month: string, delta: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** «октябрь», «October»: the month of a day, as a budget warning names it. */
export function monthName(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang, { timeZone: "UTC", month: "long" }).format(parseIsoDate(iso));
}

/** A budget warning for an entry of `day`, worded as the bot's (bot/money_texts.alert_text). */
export function alertText(alert: MoneyAlert, day: string, currency: string, lang: Lang, t: Dict): string {
  return t.money.alert({
    threshold: alert.threshold,
    percent: Math.floor((alert.spent * 100) / alert.budget),
    name: alert.emoji && alert.name ? `${alert.emoji} ${alert.name}` : null,
    month: monthName(day, lang),
    spent: formatAmount(alert.spent, currency, lang),
    budget: formatAmount(alert.budget, currency, lang),
  });
}

/** «из 30 000 ₽ · осталось 17 600 ₽, по 620 ₽ в день», or «из 30 000 ₽ · перерасход 3 000 ₽». */
export function budgetText(
  budget: number, left: number, perDay: number | null, currency: string, lang: Lang, t: Dict,
): string {
  const money = (amount: number) => formatAmount(amount, currency, lang);
  return t.money.budget({
    budget: money(budget),
    rest: money(Math.abs(left)),
    over: left < 0,
    perDay: perDay === null ? null : money(perDay),
  });
}

export type Tone = "ok" | "warning" | "over";

/** A budget's bar: how much of it is spent (0–100) and its colour — amber from 80 %, red from 100 %. */
export function budgetUse(spent: number, budget: number): { percent: number; tone: Tone } {
  const share = (spent * 100) / budget;
  return {
    percent: Math.min(100, Math.round(share)),
    tone: share >= 100 ? "over" : share >= 80 ? "warning" : "ok",
  };
}

/** The ring's colours: the five largest categories in the habit palette's order, the others in
 *  slate — as on the bot's report (money_cards.PALETTE). */
export const SLICE_COLORS = [
  "var(--habit-mint)", "var(--habit-sky)", "var(--habit-violet)", "var(--habit-rose)", "var(--habit-coral)",
] as const;
export const REST_COLOR = "var(--habit-slate)";

/** The colour of the category that is `index`-th by its amount. */
export function sliceColor(index: number): string {
  return SLICE_COLORS[index] ?? REST_COLOR;
}

export interface RingPart {
  /** A category's id; null for all the others together. */
  id: number | null;
  amount: number;
  color: string;
}

/** The five largest expenses (the API sorts them), then «Остальное» for the others, if any. */
export function ringParts(expenses: CategoryTotal[]): RingPart[] {
  const parts: RingPart[] = expenses.slice(0, SLICE_COLORS.length).map((item, index) => ({
    id: item.category_id, amount: item.amount, color: sliceColor(index),
  }));
  const rest = expenses.slice(SLICE_COLORS.length).reduce((sum, item) => sum + item.amount, 0);
  return rest > 0 ? [...parts, { id: null, amount: rest, color: REST_COLOR }] : parts;
}

/** «Сегодня», «Вчера», or «пн, 28 сент.»: the heading of a day's entries. */
export function entryDay(iso: string, today: string, lang: Lang, words: { today: string; yesterday: string }): string {
  const away = daysBetween(iso, today);
  if (away === 0) return words.today;
  if (away === 1) return words.yesterday;
  return new Intl.DateTimeFormat(lang, { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" })
    .format(parseIsoDate(iso));
}

/** The entries in groups by day, in the order they come (the API sends the newest first). */
export function byDay(entries: MoneyEntry[]): { day: string; entries: MoneyEntry[] }[] {
  const days: { day: string; entries: MoneyEntry[] }[] = [];
  for (const entry of entries) {
    const last = days.at(-1);
    if (last?.day === entry.day) last.entries.push(entry);
    else days.push({ day: entry.day, entries: [entry] });
  }
  return days;
}
