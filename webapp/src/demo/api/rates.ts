/**
 * The rates of the Bank of Russia (routers/rates.py, core/clients/cbr.py): every currency of the
 * app's settings, roubles for one unit, moving smoothly from day to day with a little noise drawn
 * from the date; the change to the bank's working day before, and thirty days of one currency.
 */
import type { RateHistory, Rates, RatesAll } from "../../api/types";
import { addDaysIso, daysBetween } from "../../lib/format";
import { currencyName } from "../../lib/money";
import type { Visit } from "./data";
import { json, notFound, route, type Route } from "./http";
import { chance, fnv1a } from "./random";
import { weekdayOf } from "./time";
import { queryText } from "./validate";

/**
 * Roubles for one unit, about the autumn of 2026: twenty of the bank's currencies (spec §5.3) — the
 * fifteen of the settings besides the rouble, and five more.
 */
const BASES: Readonly<Record<string, number>> = {
  USD: 81.5, EUR: 95.2, KZT: 0.162, BYN: 25.1, UAH: 1.97, UZS: 0.0066, KGS: 0.94, AMD: 0.212, GEL: 30.2,
  AZN: 47.9, TJS: 8.62, TRY: 1.98, CNY: 11.42, GBP: 109.4, PLN: 22.3,
  AED: 22.19, CAD: 58.6, CHF: 101.9, INR: 0.921, JPY: 0.551,
};
/** routers/rates.py's HISTORY_DAYS. */
const HISTORY_DAYS = 30;

const working = (day: string) => weekdayOf(day) < 5;

/** The bank's last working day up to `day`. */
function bankDay(day: string): string {
  let found = day;
  while (!working(found)) found = addDaysIso(found, -1);
  return found;
}

/** A currency's rate on a day: a slow wave and a faster one, and the day's noise. */
function rateOn(code: string, base: number, day: string): number {
  const phase = (fnv1a(code) % 628) / 100;
  const days = daysBetween("2026-01-01", day);
  const wave = 0.03 * Math.sin(days / 23 + phase) + 0.01 * Math.sin(days / 6 + 2 * phase);
  const noise = (chance(day, code, "rate") - 0.5) * 0.004;
  return Number((base * (1 + wave + noise)).toPrecision(6));
}

function rateOf(code: string, day: string): { value: number; change: number } {
  const base = BASES[code] ?? 1;
  const value = rateOn(code, base, day);
  return { value, change: Number((value - rateOn(code, base, bankDay(addDaysIso(day, -1)))).toPrecision(4)) };
}

/** «Сегодня»'s rates: the dollar and the euro of the bank's day. */
export function todayRates(visit: Visit): Rates {
  const day = bankDay(visit.today());
  return { date: day, usd: rateOf("USD", day), eur: rateOf("EUR", day) };
}

export const RATES: Route[] = [
  route("GET", "/rates/all", (visit) => {
    const day = bankDay(visit.today());
    const lang = visit.lang();
    // views.rates_all_out: USD, EUR and the user's currency first, the others by their names.
    const first = ["USD", "EUR", visit.data.profile.currency];
    const order = (code: string) => (first.includes(code) ? first.indexOf(code) : first.length);
    const currencies = Object.keys(BASES)
      .map((code) => ({ code, name: currencyName(code, lang), ...rateOf(code, day) }))
      .sort((a, b) => order(a.code) - order(b.code) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    return json<RatesAll>({ date: day, currencies });
  }),
  route("GET", "/rates/history", (visit, { query }) => {
    const code = queryText(query, "code", { required: true, pattern: /^[A-Z]{3}$/ }) ?? "";
    const base = BASES[code];
    if (base === undefined) throw notFound("currency");
    const today = visit.today();
    const points = Array.from({ length: HISTORY_DAYS + 1 }, (_, index) => addDaysIso(today, index - HISTORY_DAYS))
      .filter(working)
      .map((day) => ({ day, value: rateOn(code, base, day) }));
    return json<RateHistory>({ code, points });
  }),
];
