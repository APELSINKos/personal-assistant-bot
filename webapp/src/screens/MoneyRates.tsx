import { ArrowLeftRight } from "lucide-react";
import { useState } from "react";
import { useRateHistory, useRatesAll } from "../api/money";
import type { CurrencyRate } from "../api/types";
import { AmountField } from "../components/AmountField";
import { Card } from "../components/Card";
import { LineChart } from "../components/MoneyCharts";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT } from "../i18n";
import { dayMonth, formatNumber } from "../lib/format";
import { convert, currencyName, formatRate, historyWords, parseAmount, rateChange } from "../lib/money";

/** The bank's rates of the day, a currency's 30 days, and a converter between any two currencies. */
export function MoneyRates() {
  const t = useT();
  const lang = useLang();
  const rates = useRatesAll();
  const [code, setCode] = useState("USD");
  if (rates.isPending) return <Loader />;
  // A failed refresh keeps the rates and the converter: only a first load that failed is an error.
  if (rates.isLoadingError) {
    return <ErrorState text={t.money.ratesUnavailable} onRetry={() => void rates.refetch()} />;
  }
  const list = rates.data.currencies;
  const chosen = list.find((rate) => rate.code === code) ?? list[0];
  return (
    <>
      <h1 className="screen__title">{t.money.rates}</h1>
      <p className="muted money-form__hint">{t.money.ratesOn(dayMonth(rates.data.date, lang, true))}</p>
      {chosen && (
        <Card index={0}>
          <label className="field">
            <span className="field__label">{t.money.currency}</span>
            <select className="input" value={chosen.code} onChange={(event) => setCode(event.target.value)}>
              {list.map((rate) => (
                <option key={rate.code} value={rate.code}>{`${rate.code} — ${rate.name}`}</option>
              ))}
            </select>
          </label>
          <p className="rate-now">
            <span className="rate-now__value">{formatRate(chosen.value, lang)}</span>
            <span className="muted">{rateChange(chosen, lang)}</span>
          </p>
          <History rate={chosen} />
        </Card>
      )}
      <Converter rates={list} />
    </>
  );
}

function History({ rate }: { rate: CurrencyRate }) {
  const t = useT();
  const lang = useLang();
  const history = useRateHistory(rate.code);
  if (history.isPending) return <div className="skeleton" />;
  if (history.isLoadingError || history.data.points.length < 2) {
    return <p className="muted">{t.money.historyUnavailable}</p>;
  }
  return (
    <>
      <LineChart points={history.data.points} label={t.money.chart(rate.name)} lang={lang} />
      <p className="muted line-chart__summary">{t.money.history(historyWords(history.data.points, lang))}</p>
    </>
  );
}

function Converter({ rates }: { rates: CurrencyRate[] }) {
  const t = useT();
  const lang = useLang();
  const [amount, setAmount] = useState("100");
  const [from, setFrom] = useState("USD");
  const [to, setTo] = useState("RUB");
  const value = parseAmount(amount);
  const result = value === null ? null : convert(Number(value), from, to, rates);
  const options = [{ code: "RUB", name: currencyName("RUB", lang) }, ...rates];
  const select = (label: string, current: string, onChange: (code: string) => void) => (
    <label className="field">
      <span className="field__label">{label}</span>
      <select className="input" value={current} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.code} value={option.code}>{`${option.code} — ${option.name}`}</option>
        ))}
      </select>
    </label>
  );
  return (
    <Card title={t.money.converter} index={1}>
      <AmountField
        label={t.money.amount}
        value={amount}
        sign={from}
        invalid={amount.trim() !== "" && value === null}
        onChange={setAmount}
      />
      <div className="converter">
        {select(t.money.from, from, setFrom)}
        <button
          type="button"
          className="icon-button converter__swap"
          aria-label={t.money.swap}
          onClick={() => {
            setFrom(to);
            setTo(from);
          }}
        >
          <ArrowLeftRight size={20} aria-hidden />
        </button>
        {select(t.money.to, to, setTo)}
      </div>
      <p className="converter__result" aria-live="polite">
        {result === null ? "—" : `${formatNumber(result, lang, 2)} ${to}`}
      </p>
    </Card>
  );
}
