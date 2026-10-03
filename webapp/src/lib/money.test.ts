import { describe, expect, it } from "vitest";
import type { MoneyAlert } from "../api/types";
import { dict } from "../i18n";
import {
  addMonths, alertText, amountText, CATEGORY_EMOJI, CURRENCIES, currencySign, formatAmount, formatSigned, monthName,
  monthOf, parseAmount,
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
