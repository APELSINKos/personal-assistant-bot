import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoneyRates } from "./MoneyRates";

const RATES = {
  date: "2026-09-28",
  currencies: [
    { code: "USD", name: "Доллар США", value: 82.6417, change: -0.45 },
    { code: "EUR", name: "Евро", value: 96.1234, change: 0.31 },
    { code: "AMD", name: "Армянский драм", value: 0.2149, change: 0 },
  ],
};

function history(code: string, values: number[]) {
  return { code, points: values.map((value, index) => ({ day: `2026-09-${String(index + 1).padStart(2, "0")}`, value })) };
}

describe("Rates", () => {
  it("shows a currency's rate and its 30 days, and another's when chosen", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /rates/all": RATES,
      "GET /rates/history?code=USD": history("USD", [84, 85.1, 81.9, 82.64]),
      "GET /rates/history?code=EUR": history("EUR", [95, 96.12]),
    });
    renderWithApp(<MoneyRates />, { path: "/money/rates" });
    expect(await screen.findByText("На 28 сентября 2026")).toBeInTheDocument();
    expect(screen.getByText("82,64 ₽")).toBeInTheDocument();
    expect(screen.getByText("▼ 0,45")).toBeInTheDocument();
    expect(
      await screen.findByText("За 30 дней: с 84,00 ₽ до 82,64 ₽ (−1,36 ₽, −1,6 %); минимум 81,90 ₽, максимум 85,10 ₽"),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Курс: Доллар США, за 30 дней" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Валюта"), { target: { value: "EUR" } });
    expect(await screen.findByText(/с 95,00 ₽ до 96,12 ₽/)).toBeInTheDocument();
    expect(calls.map((call) => call.path)).toContain("/rates/history?code=EUR");
  });

  it("converts any two currencies through the rouble, either way round", async () => {
    installTelegram();
    mockApi({ "GET /rates/all": RATES, "GET /rates/history?code=USD": history("USD", [84, 82.64]) });
    renderWithApp(<MoneyRates />, { path: "/money/rates" });
    expect(await screen.findByText("8 264,17 RUB")).toBeInTheDocument(); // 100 USD
    fireEvent.click(screen.getByRole("button", { name: "Поменять валюты местами" }));
    expect(screen.getByText("1,21 USD")).toBeInTheDocument(); // 100 RUB
    fireEvent.change(screen.getByLabelText("Из"), { target: { value: "AMD" } });
    expect(screen.getByText("0,26 USD")).toBeInTheDocument(); // 100 drams
    fireEvent.change(screen.getByLabelText("Сумма"), { target: { value: "много" } });
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Сумма — число больше нуля, не больше двух знаков после запятой")).toBeInTheDocument();
  });

  it("says when the bank's rates cannot be had", async () => {
    installTelegram();
    mockApi({ "GET /rates/all": { status: 404, body: { status: 404, code: "not_found" } } });
    renderWithApp(<MoneyRates />, { path: "/money/rates" });
    expect(await screen.findByText("Курсы ЦБ сейчас недоступны")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});
