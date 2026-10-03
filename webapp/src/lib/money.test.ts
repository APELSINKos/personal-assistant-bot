import { describe, expect, it } from "vitest";
import type { MoneyAlert } from "../api/types";
import { dict } from "../i18n";
import {
  addMonths, alertText, amountText, budgetText, budgetUse, byDay, CATEGORY_EMOJI, convert, CURRENCIES, currencyName,
  currencySign, entryDay, formatAmount, formatRate, formatSigned, historyWords, monthName, monthOf, parseAmount,
  rateChange, ringParts, sliceColor,
} from "./money";

/** An amount as it shows: its spaces are no-break ones. */
const shown = (text: string) => text.replaceAll(" ", "\u00a0");

describe("currencies and emoji", () => {
  it("has the server's 16 currencies and 40 emoji", () => {
    expect(Object.keys(CURRENCIES)).toHaveLength(16);
    expect(Object.keys(CURRENCIES)[0]).toBe("RUB");
    expect(new Set(CATEGORY_EMOJI).size).toBe(40);
    expect([currencySign("KZT"), currencySign("XYZ")]).toEqual(["₸", "XYZ"]);
  });
});

describe("amounts", () => {
  it("groups thousands and shows kopecks only when there are some", () => {
    expect(formatAmount(25000, "RUB", "ru")).toBe(shown("250 ₽"));
    expect(formatAmount(120000, "RUB", "ru")).toBe(shown("1 200 ₽"));
    expect(formatAmount(43050, "RUB", "ru")).toBe(shown("430,50 ₽"));
    expect(formatAmount(43050, "RUB", "en")).toBe(shown("430.50 ₽"));
    expect(formatAmount(120000, "RUB", "en")).toBe(shown("1,200 ₽"));
    expect(formatAmount(100_000_000_000, "RUB", "ru")).toBe(shown("1 000 000 000 ₽"));
  });

  it("puts the dollar, the euro and the pound first in English only", () => {
    expect(formatAmount(120000, "USD", "en")).toBe("$1,200");
    expect(formatAmount(5, "GBP", "en")).toBe("£0.05");
    expect(formatAmount(120000, "USD", "ru")).toBe(shown("1 200 $"));
    expect(formatAmount(500000, "KZT", "en")).toBe(shown("5,000 ₸"));
  });

  it("marks an income and a balance", () => {
    expect(formatAmount(500000, "RUB", "ru", true)).toBe(shown("+5 000 ₽"));
    expect(formatSigned(1260000, "RUB", "ru")).toBe(shown("+12 600 ₽"));
    expect(formatSigned(-300000, "RUB", "ru")).toBe(shown("−3 000 ₽"));
  });

  it("reads a typed amount as the API takes it", () => {
    expect(parseAmount("250")).toBe("250");
    expect(parseAmount(" 1 200 ")).toBe("1200");
    expect(parseAmount("430,5")).toBe("430.50");
    expect(parseAmount("430.05")).toBe("430.05");
    expect(parseAmount("0250")).toBe("250");
    expect(parseAmount("0,5")).toBe("0.50");
    expect(parseAmount("1000000000")).toBe("1000000000");
    for (const wrong of ["", "0", "0,00", "1,234", "12a", "-5", "+5", "1000000000,01", "1e3", "12,", ",5"]) {
      expect(parseAmount(wrong), wrong).toBeNull();
    }
  });

  it("puts an amount back into its field", () => {
    expect(amountText(120000, "ru")).toBe("1200");
    expect(amountText(43050, "ru")).toBe("430,50");
    expect(amountText(43005, "en")).toBe("430.05");
  });
});

describe("months", () => {
  it("steps over the year's end both ways", () => {
    expect(monthOf("2026-10-03")).toBe("2026-10");
    expect(addMonths("2026-12", 1)).toBe("2027-01");
    expect(addMonths("2026-01", -1)).toBe("2025-12");
    expect(addMonths("2026-10", -13)).toBe("2025-09");
  });

  it("names a month as a warning does", () => {
    expect(monthName("2026-10-03", "ru")).toBe("октябрь");
    expect(monthName("2026-10-03", "en")).toBe("October");
  });
});

describe("budget warnings", () => {
  const total: MoneyAlert = {
    category_id: null, emoji: null, name: null, threshold: 80, spent: 2410000, budget: 3000000,
  };
  const cafe: MoneyAlert = { category_id: 2, emoji: "☕", name: "Кафе", threshold: 100, spent: 530000, budget: 500000 };

  it("are worded as the bot's", () => {
    const ru = (alert: MoneyAlert) => alertText(alert, "2026-10-03", "RUB", "ru", dict("ru"));
    expect(ru(total)).toBe("⚠️ Потрачено 80\u00a0% бюджета на октябрь: 24\u00a0100\u00a0₽ из 30\u00a0000\u00a0₽");
    expect(ru({ ...total, threshold: 100, spent: 3010000 })).toBe(
      "🚨 Бюджет на октябрь закончился: 30\u00a0100\u00a0₽ из 30\u00a0000\u00a0₽",
    );
    expect(ru({ ...cafe, threshold: 80, spent: 410000 })).toBe(
      "⚠️ Потрачено 82\u00a0% бюджета «☕ Кафе» на октябрь: 4\u00a0100\u00a0₽ из 5\u00a0000\u00a0₽",
    );
    expect(ru(cafe)).toBe("🚨 Бюджет «☕ Кафе» на октябрь закончился: 5\u00a0300\u00a0₽ из 5\u00a0000\u00a0₽");
  });

  it("are in English with the user's currency", () => {
    const en = (alert: MoneyAlert) => alertText(alert, "2026-10-03", "USD", "en", dict("en"));
    expect(en(total)).toBe("⚠️ 80% of the October budget is spent: $24,100 of $30,000");
    expect(en({ ...cafe, name: "Eating out" })).toBe(
      "🚨 The “☕ Eating out” budget for October has run out: $5,300 of $5,000",
    );
  });
});

describe("the month's parts", () => {
  it("word a budget's rest, for each day or overspent", () => {
    expect(budgetText(3000000, 1760000, 62000, "RUB", "ru", dict("ru"))).toBe(
      `из ${shown("30 000 ₽")} · осталось ${shown("17 600 ₽")}, по ${shown("620 ₽")} в день`,
    );
    expect(budgetText(500000, -30000, null, "RUB", "ru", dict("ru"))).toBe(
      `из ${shown("5 000 ₽")} · перерасход ${shown("300 ₽")}`,
    );
    expect(budgetText(3000000, 0, null, "USD", "en", dict("en"))).toBe("of $30,000 · $0 left");
  });

  it("colour a budget amber from 80 % and red from 100 %", () => {
    expect(budgetUse(2370000, 3000000)).toEqual({ percent: 79, tone: "ok" });
    expect(budgetUse(2400000, 3000000)).toEqual({ percent: 80, tone: "warning" });
    expect(budgetUse(3000000, 3000000)).toEqual({ percent: 100, tone: "over" });
    expect(budgetUse(4500000, 3000000)).toEqual({ percent: 100, tone: "over" });
  });

  it("ring the five largest categories and the others together", () => {
    const expenses = [9, 8, 7, 6, 5, 4, 3].map((amount, index) => ({
      category_id: index + 1, amount, share: 0, left: null,
    }));
    expect(ringParts(expenses)).toEqual([
      { id: 1, amount: 9, color: "var(--habit-mint)" },
      { id: 2, amount: 8, color: "var(--habit-sky)" },
      { id: 3, amount: 7, color: "var(--habit-violet)" },
      { id: 4, amount: 6, color: "var(--habit-rose)" },
      { id: 5, amount: 5, color: "var(--habit-coral)" },
      { id: null, amount: 7, color: "var(--habit-slate)" },
    ]);
    expect(ringParts(expenses.slice(0, 2)).map((part) => part.id)).toEqual([1, 2]);
    expect(sliceColor(7)).toBe("var(--habit-slate)");
  });

  it("head each day of entries", () => {
    const words = dict("ru").calendar.words;
    expect(entryDay("2026-09-28", "2026-09-28", "ru", words)).toBe("Сегодня");
    expect(entryDay("2026-09-27", "2026-09-28", "ru", words)).toBe("Вчера");
    expect(entryDay("2026-09-25", "2026-09-28", "ru", words)).toBe("пт, 25 сент.");
    expect(entryDay("2026-09-25", "2026-09-28", "en", dict("en").calendar.words)).toBe("Fri, Sep 25");
  });

  it("group the entries by day, in their order", () => {
    const entry = (id: number, day: string) => ({ id, amount: 100, category_id: 1, note: "", day });
    expect(byDay([entry(3, "2026-09-28"), entry(2, "2026-09-27"), entry(1, "2026-09-27")])).toEqual([
      { day: "2026-09-28", entries: [entry(3, "2026-09-28")] },
      { day: "2026-09-27", entries: [entry(2, "2026-09-27"), entry(1, "2026-09-27")] },
    ]);
  });
});

describe("rates", () => {
  const usd = { code: "USD", name: "Доллар США", value: 82.6417, change: -0.45 };
  const eur = { code: "EUR", name: "Евро", value: 96.1234, change: 0.31 };
  const amd = { code: "AMD", name: "Армянский драм", value: 0.2149, change: 0 };

  it("convert any two currencies through the rouble", () => {
    expect(convert(100, "USD", "RUB", [usd, eur])).toBeCloseTo(8264.17, 2);
    expect(convert(100, "RUB", "EUR", [usd, eur])).toBeCloseTo(1.04, 2);
    expect(convert(10, "EUR", "USD", [usd, eur])).toBeCloseTo(11.63, 2);
    expect(convert(5, "RUB", "RUB", [])).toBe(5);
    expect(convert(1, "GBP", "RUB", [usd, eur])).toBeNull();
  });

  it("show a rate with more digits under ten roubles, and its day's change", () => {
    expect(formatRate(82.6417, "ru")).toBe(shown("82,64 ₽"));
    expect(formatRate(82.6417, "en")).toBe(shown("82.64 ₽"));
    expect(formatRate(0.2149, "ru")).toBe(shown("0,2149 ₽"));
    expect(rateChange(usd, "ru")).toBe(shown("▼ 0,45"));
    expect(rateChange(eur, "en")).toBe(shown("▲ 0.31"));
    expect(rateChange(amd, "ru")).toBe(shown("• 0,0000"));
  });

  it("name a currency in the user's language", () => {
    expect(currencyName("RUB", "ru")).toBe("Российский рубль");
    expect(currencyName("EUR", "en")).toBe("Euro");
  });

  it("tell a rate's days in words", () => {
    const points = [84, 85.1, 81.9, 82.64].map((value, index) => ({ day: `2026-09-0${index + 1}`, value }));
    expect(historyWords(points, "ru")).toEqual({
      first: shown("84,00 ₽"),
      last: shown("82,64 ₽"),
      change: shown("−1,36 ₽"),
      percent: shown("−1,6 %"),
      low: shown("81,90 ₽"),
      high: shown("85,10 ₽"),
    });
    expect(dict("en").money.history(historyWords(points, "en"))).toBe(
      `Over 30 days: from ${shown("84.00 ₽")} to ${shown("82.64 ₽")} (${shown("−1.36 ₽")}, −1.6%); `
        + `low ${shown("81.90 ₽")}, high ${shown("85.10 ₽")}`,
    );
  });
});
