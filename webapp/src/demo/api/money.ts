/**
 * Money (routers/money.py, services/money.py and services/money_month.py): a month with its totals by
 * category and by day and the budget's rest; the entries, the categories and the budgets, checked as
 * the server checks them; and the budget warnings an expense sets off — at 80 % and at 100 %, once a
 * month per budget and threshold, the higher one shown when both are reached at once.
 */
import type {
  Me, MoneyAlert, MoneyCategory, MoneyEntry, MoneyEntrySaved, MoneyKind, MoneyMonth, TodayMoney,
} from "../../api/types";
import { addDaysIso, codePoints, daysBetween } from "../../lib/format";
import { AMOUNT_MAX, CATEGORY_EMOJI, CATEGORY_LIMIT, ENTRY_DAYS_BACK } from "../../lib/money";
import type { StoredCategory, Visit } from "./data";
import { created, invalidInput, json, limitReached, noContent, notFound, route, type Route } from "./http";
import { meOut } from "./me";
import { monthLength, monthStart, nextMonth } from "./time";
import { check, ID_MAX, itemId, queryText, type Fields } from "./validate";
import { TEXTS } from "./words";

/** LIMITS: the length of an entry's note and of a category's name; the entries of a user and of a month. */
const NOTE_LENGTH = 100;
const NAME_LENGTH = 30;
const ENTRIES = 50_000;
const ENTRIES_MONTH = 1000;
/** money_month.THRESHOLDS: percent of a budget. */
const THRESHOLDS = [80, 100];
/** The fallback of each kind (money_style.OTHER): never hidden, so a guess has somewhere to go. */
const OTHER = { expense: "other", income: "other_in" } as const;

/** schemas.Amount: a decimal with a point, in the user's currency. */
const AMOUNT = /^[0-9]{1,12}(\.[0-9]{1,2})?$/;
const ENTRY_PATCH: Fields = {
  amount: { type: "str", nullable: true, pattern: AMOUNT },
  category_id: { type: "int", nullable: true, ge: 1, le: ID_MAX },
  note: { type: "str", nullable: true, max: 1000 },
  day: { type: "date", nullable: true },
};
const ENTRY_IN: Fields = {
  ...ENTRY_PATCH,
  amount: { type: "str", required: true, pattern: AMOUNT },
  category_id: { type: "int", required: true, ge: 1, le: ID_MAX },
  note: { type: "str", max: 1000 },
};
const CATEGORY_IN: Fields = {
  kind: { type: "str", required: true, choices: ["expense", "income"] },
  name: { type: "str", required: true, max: 1000 },
  emoji: { type: "str", required: true, max: 16 },
};
const CATEGORY_PATCH: Fields = {
  name: { type: "str", nullable: true, max: 1000 },
  emoji: { type: "str", nullable: true, max: 16 },
  hidden: { type: "bool", nullable: true },
  budget: { type: "str", nullable: true, pattern: AMOUNT },
};
const BUDGET_IN: Fields = { amount: { type: "str", required: true, nullable: true, pattern: AMOUNT } };

interface EntryInput {
  amount?: string | null;
  category_id?: number | null;
  note?: string | null;
  day?: string | null;
}

/** views.hundredths: «430.50» is 43050. */
function hundredths(amount: string): number {
  const [whole = "0", part = ""] = amount.split(".");
  return Number(whole) * 100 + Number(part.padEnd(2, "0"));
}

/** money._check_amount: above zero and at most a billion. */
function checkAmount(amount: number, field = "amount"): number {
  if (!(amount > 0 && amount <= AMOUNT_MAX)) throw invalidInput({ field, reason: "out_of_range" });
  return amount;
}

/** money._clean_text: control characters (C0 and DEL) as spaces, one space between words, within the limit. */
function cleanText(text: string, limit: number, field: string): string {
  const spaced = Array.from(text, (char) => (char.charCodeAt(0) <= 0x1f || char === "\u007f" ? " " : char)).join("");
  const cleaned = spaced.split(/\s+/).filter(Boolean).join(" ");
  if (codePoints(cleaned) > limit) throw invalidInput({ field, reason: "length", limit });
  return cleaned;
}

function nameOf(visit: Visit, category: StoredCategory): string {
  return category.name ?? (category.preset ? TEXTS[visit.lang()].presets[category.preset] : "");
}

export function categoryOut(visit: Visit, category: StoredCategory): MoneyCategory {
  return {
    id: category.id, kind: category.kind, name: nameOf(visit, category), emoji: category.emoji, hidden: category.hidden,
    can_hide: category.preset !== OTHER[category.kind], budget: category.budget,
  };
}

function categoryOf(visit: Visit, id: number): StoredCategory {
  const found = visit.data.categories.find((category) => category.id === id);
  if (!found) throw notFound("category");
  return found;
}

const kindOf = (visit: Visit, entry: MoneyEntry): MoneyKind | undefined =>
  visit.data.categories.find((category) => category.id === entry.category_id)?.kind;

/** The month's expenses from its first day: all of them, or one category's. */
function spentIn(visit: Visit, first: string, category?: number): number {
  return visit.data.entries
    .filter((entry) => entry.day.startsWith(first.slice(0, 7)) && kindOf(visit, entry) === "expense")
    .filter((entry) => category === undefined || entry.category_id === category)
    .reduce((sum, entry) => sum + entry.amount, 0);
}

/** money_month.month: the month's totals, by category and by day, and the budget's rest. */
function monthOf(visit: Visit, first: string): Omit<MoneyMonth, "first_month" | "categories"> {
  const today = visit.today();
  const key = first.slice(0, 7);
  const entries = visit.data.entries
    .filter((entry) => entry.day.startsWith(key))
    .sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : b.id - a.id));
  const byCategory = new Map<number, number>();
  const byDay = new Map<string, number>();
  let spent = 0;
  let income = 0;
  for (const entry of entries) {
    byCategory.set(entry.category_id, (byCategory.get(entry.category_id) ?? 0) + entry.amount);
    if (kindOf(visit, entry) === "expense") {
      spent += entry.amount;
      byDay.set(entry.day, (byDay.get(entry.day) ?? 0) + entry.amount);
    } else {
      income += entry.amount;
    }
  }
  const position = (id: number) => visit.data.categories.findIndex((category) => category.id === id);
  const totals = (kind: MoneyKind) =>
    [...byCategory]
      .flatMap(([id, amount]) => {
        const category = visit.data.categories.find((item) => item.id === id);
        if (category?.kind !== kind) return [];
        const shareOf = kind === "expense" && spent ? Math.floor((200 * amount + spent) / (2 * spent)) : 0;
        return [{ category_id: id, amount, share: shareOf, left: category.budget === null ? null : category.budget - amount }];
      })
      .sort((a, b) => b.amount - a.amount || position(a.category_id) - position(b.category_id));
  const budget = visit.data.profile.budget;
  const left = budget === null ? null : budget - spent;
  const current = monthStart(today) === first;
  return {
    month: key, currency: visit.data.profile.currency, spent, income, balance: income - spent, budget, left,
    per_day: left !== null && left > 0 && current ? Math.floor(left / daysBetween(today, nextMonth(today))) : null,
    expenses: totals("expense"), incomes: totals("income"),
    days: Array.from({ length: monthLength(first) }, (_, offset) => {
      const day = addDaysIso(first, offset);
      return day <= today ? (byDay.get(day) ?? 0) : null;
    }),
    entries,
  };
}

/** «Сегодня»'s money: this month's and today's. */
export function todayMoney(visit: Visit): TodayMoney {
  const month = monthOf(visit, monthStart(visit.today()));
  return {
    currency: month.currency, today: month.days[Number(visit.today().slice(8)) - 1] ?? 0, spent: month.spent,
    budget: month.budget, left: month.left, per_day: month.per_day, count: month.entries.length,
  };
}

/** A budget's warnings forgotten: one that changed warns afresh. 0 is the budget of all expenses. */
function forgetAlerts(visit: Visit, scope: number): void {
  for (const key of [...visit.data.alerts]) if (key.split("/")[1] === String(scope)) visit.data.alerts.delete(key);
}

/**
 * money.rearm: the warnings of a day's month that no longer hold — an entry undone or corrected took
 * the spending back under the threshold, or the budget is gone — warn again when it is reached.
 */
function rearm(visit: Visit, day: string): void {
  const month = day.slice(0, 7);
  for (const key of [...visit.data.alerts]) {
    const [shown, scope = "0", threshold = "0"] = key.split("/");
    if (shown !== month) continue;
    const budget = scope === "0"
      ? visit.data.profile.budget
      : (visit.data.categories.find((category) => category.id === Number(scope))?.budget ?? null);
    const spent = spentIn(visit, monthStart(day), scope === "0" ? undefined : Number(scope));
    if (budget === null || spent * 100 < budget * Number(threshold)) visit.data.alerts.delete(key);
  }
}

/** money_month.alerts_after: the warnings an expense of this month sets off, the higher one of two reached at once. */
function alertsAfter(visit: Visit, entry: MoneyEntry): MoneyAlert[] {
  const first = monthStart(visit.today());
  const category = categoryOf(visit, entry.category_id);
  if (category.kind !== "expense" || monthStart(entry.day) !== first) return [];
  const found: MoneyAlert[] = [];
  for (const [scope, budget] of [[category, category.budget], [null, visit.data.profile.budget]] as const) {
    if (budget === null) continue;
    const spent = spentIn(visit, first, scope?.id);
    const fresh = THRESHOLDS.filter((threshold) => {
      const key = `${first.slice(0, 7)}/${scope?.id ?? 0}/${threshold}`;
      if (spent * 100 < budget * threshold || visit.data.alerts.has(key)) return false;
      visit.data.alerts.add(key);
      return true;
    });
    if (fresh.length) {
      found.push({
        category_id: scope?.id ?? null, emoji: scope?.emoji ?? null, name: scope ? nameOf(visit, scope) : null,
        threshold: Math.max(...fresh) as MoneyAlert["threshold"], spent, budget,
      });
    }
  }
  return found;
}

/** money._check_day: a day of the last year up to today; today when left out. */
function checkDay(visit: Visit, day: string | null | undefined): string {
  const today = visit.today();
  if (day == null) return today;
  if (day < addDaysIso(today, -ENTRY_DAYS_BACK) || day > today) throw invalidInput({ field: "day", reason: "out_of_range" });
  return day;
}

/** The month of a day has room for one more entry: a new one or one moved in. */
function checkMonth(visit: Visit, day: string): void {
  const inMonth = visit.data.entries.filter((entry) => entry.day.startsWith(day.slice(0, 7))).length;
  if (inMonth >= ENTRIES_MONTH) throw limitReached("entry_month", ENTRIES_MONTH);
}

function entryOf(visit: Visit, raw: string): MoneyEntry {
  const id = itemId(raw, "entry_id");
  const found = visit.data.entries.find((entry) => entry.id === id);
  if (!found) throw notFound("entry");
  return found;
}

/** money.check_name: a name of its own among the categories of its kind, a preset's in either language too. */
function checkName(visit: Visit, kind: MoneyKind, name: string, own?: StoredCategory): string {
  const cleaned = cleanText(name, NAME_LENGTH, "name");
  if (!cleaned) throw invalidInput({ field: "name", reason: "empty" });
  const same = (a: string, b: string) => a.toLowerCase().replaceAll("ё", "е") === b.toLowerCase().replaceAll("ё", "е");
  for (const other of visit.data.categories) {
    if (other === own || other.kind !== kind) continue;
    const names = other.name !== null ? [other.name] : other.preset ? [TEXTS.ru.presets[other.preset], TEXTS.en.presets[other.preset]] : [];
    if (names.some((known) => same(cleaned, known))) throw invalidInput({ field: "name", reason: "duplicate" });
  }
  return cleaned;
}

function checkEmoji(emoji: string): void {
  if (!(CATEGORY_EMOJI as readonly string[]).includes(emoji)) throw invalidInput({ field: "emoji", reason: "not_in_set" });
}

function saved(visit: Visit, entry: MoneyEntry): MoneyEntrySaved {
  return { entry: { ...entry }, alerts: alertsAfter(visit, entry) };
}

/** routers/money.py's _first: the month asked for, of the years the server keeps; this one when left out. */
function firstOf(visit: Visit, month: string | null): string {
  if (month === null) return monthStart(visit.today());
  const number = Number(month.slice(5));
  if (number < 1 || number > 12) throw invalidInput({ field: "month", reason: "format" });
  const year = Number(month.slice(0, 4));
  if (year < 2000 || year > 2100) throw invalidInput({ field: "month", reason: "range" });
  return `${month}-01`;
}

export const MONEY: Route[] = [
  route("GET", "/money", (visit, { query }) => {
    const first = firstOf(visit, queryText(query, "month", { pattern: /^[0-9]{4}-[0-9]{2}$/ }));
    const oldest = visit.data.entries.map((entry) => entry.day).sort()[0];
    return json<MoneyMonth>({
      ...monthOf(visit, first), first_month: oldest ? oldest.slice(0, 7) : null,
      categories: visit.data.categories.map((category) => categoryOut(visit, category)),
    });
  }),
  route("POST", "/money/entries", (visit, { body }) => {
    check(body, ENTRY_IN);
    const input = body as EntryInput & { amount: string; category_id: number };
    const amount = checkAmount(hundredths(input.amount));
    categoryOf(visit, input.category_id);
    const note = cleanText(input.note ?? "", NOTE_LENGTH, "note");
    const day = checkDay(visit, input.day);
    if (visit.data.entries.length >= ENTRIES) throw limitReached("entry", ENTRIES);
    checkMonth(visit, day);
    const entry: MoneyEntry = { id: visit.data.next.entry++, amount, category_id: input.category_id, note, day };
    visit.data.entries.push(entry);
    return created<MoneyEntrySaved>(saved(visit, entry));
  }),
  route("GET", "/money/entries/{entry_id}", (visit, { params }) =>
    json<MoneyEntry>({ ...entryOf(visit, params.entry_id ?? "") })),
  route("PATCH", "/money/entries/{entry_id}", (visit, { params, body }) => {
    const raw = params.entry_id ?? "";
    itemId(raw, "entry_id");
    check(body, ENTRY_PATCH);
    const patch = body as EntryInput;
    const entry = entryOf(visit, raw);
    const old = entry.day;
    // Every field is checked before any changes.
    const amount = patch.amount == null ? null : checkAmount(hundredths(patch.amount));
    if (patch.category_id != null) categoryOf(visit, patch.category_id);
    const note = patch.note == null ? null : cleanText(patch.note, NOTE_LENGTH, "note");
    if (patch.day != null && patch.day !== entry.day) {
      checkDay(visit, patch.day);
      if (patch.day.slice(0, 7) !== entry.day.slice(0, 7)) checkMonth(visit, patch.day);
    }
    Object.assign(entry, {
      amount: amount ?? entry.amount, category_id: patch.category_id ?? entry.category_id, note: note ?? entry.note,
      day: patch.day ?? entry.day,
    });
    rearm(visit, old);
    if (entry.day.slice(0, 7) !== old.slice(0, 7)) rearm(visit, entry.day);
    return json<MoneyEntrySaved>(saved(visit, entry));
  }),
  route("DELETE", "/money/entries/{entry_id}", (visit, { params }) => {
    const entry = entryOf(visit, params.entry_id ?? "");
    visit.data.entries = visit.data.entries.filter((item) => item !== entry);
    rearm(visit, entry.day);
    return noContent();
  }),
  route("GET", "/money/categories", (visit) =>
    json<MoneyCategory[]>(visit.data.categories.map((category) => categoryOut(visit, category)))),
  route("POST", "/money/categories", (visit, { body }) => {
    check(body, CATEGORY_IN);
    const input = body as { kind: MoneyKind; name: string; emoji: string };
    checkEmoji(input.emoji);
    if (visit.data.categories.length >= CATEGORY_LIMIT) throw limitReached("category", CATEGORY_LIMIT);
    const name = checkName(visit, input.kind, input.name);
    const category: StoredCategory = {
      id: visit.data.next.category++, kind: input.kind, preset: null, name, emoji: input.emoji, hidden: false, budget: null,
    };
    visit.data.categories.push(category);
    return created<MoneyCategory>(categoryOut(visit, category));
  }),
  route("PATCH", "/money/categories/{category_id}", (visit, { params, body }) => {
    const id = itemId(params.category_id ?? "", "category_id");
    check(body, CATEGORY_PATCH);
    const patch = body as { name?: string | null; emoji?: string | null; hidden?: boolean | null; budget?: string | null };
    const category = categoryOf(visit, id);
    const name = patch.name == null ? null : checkName(visit, category.kind, patch.name, category);
    if (patch.emoji != null) checkEmoji(patch.emoji);
    if (patch.hidden && category.preset === OTHER[category.kind]) throw invalidInput({ field: "hidden", reason: "fallback" });
    // `budget: null` removes the budget; a budget left out stays as it is.
    const budgetGiven = Object.hasOwn(patch, "budget");
    let budget = category.budget;
    if (budgetGiven) {
      if (category.kind !== "expense") throw invalidInput({ field: "budget", reason: "income" });
      budget = patch.budget == null ? null : checkAmount(hundredths(patch.budget), "budget");
    }
    if (budget !== category.budget) forgetAlerts(visit, category.id);
    Object.assign(category, {
      name: name ?? category.name, emoji: patch.emoji ?? category.emoji, hidden: patch.hidden ?? category.hidden, budget,
    });
    return json<MoneyCategory>(categoryOut(visit, category));
  }),
  route("PUT", "/money/budget", (visit, { body }) => {
    check(body, BUDGET_IN);
    const { amount } = body as { amount: string | null };
    const budget = amount === null ? null : checkAmount(hundredths(amount));
    if (budget !== visit.data.profile.budget) forgetAlerts(visit, 0);
    visit.data.profile.budget = budget;
    return json<Me>(meOut(visit));
  }),
];
