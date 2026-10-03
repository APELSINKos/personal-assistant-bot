import { ChevronLeft, ChevronRight } from "lucide-react";
import { type CSSProperties, useState } from "react";
import { Link } from "wouter";
import { useDeleteEntry, useMoneyMonth, useRateHistory, useRatesAll } from "../api/money";
import { useMe } from "../api/queries";
import type { CurrencyRate, MoneyCategory, MoneyMonth } from "../api/types";
import { Card } from "../components/Card";
import { Fab } from "../components/Fab";
import { BudgetBar, DayBars, Ring, Sparkline } from "../components/MoneyCharts";
import { Empty, ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useLang, useT } from "../i18n";
import { dayMonth, localTodayIso, monthTitle } from "../lib/format";
import {
  addMonths, budgetText, byDay, entryDay, formatAmount, formatRate, formatSigned, monthOf, percentText, rateChange,
  ringParts, sliceColor,
} from "../lib/money";

type Categories = Map<number, MoneyCategory>;

/** The month's money; «today» is the city's, so the screen waits for `/me` to name its zone. */
export function MoneyScreen() {
  const me = useMe();
  // A failed refresh keeps what is shown: only a first load that failed is an error.
  if (me.isLoadingError) return <ErrorState onRetry={() => void me.refetch()} />;
  if (me.isPending) return <Loader />;
  return <MonthView today={localTodayIso(me.data.city.timezone)} />;
}

function MonthView({ today }: { today: string }) {
  const t = useT();
  const lang = useLang();
  const current = monthOf(today);
  const [shown, setShown] = useState(current);
  const [filter, setFilter] = useState<number | null>(null);
  const month = useMoneyMonth(shown);
  const first = month.data?.first_month ?? null;
  const go = (step: number) => {
    setShown(addMonths(shown, step));
    setFilter(null);
  };
  return (
    <>
      <header className="month-head money-head">
        <button
          type="button"
          className="icon-button"
          aria-label={t.money.prevMonth}
          disabled={first === null || shown <= first}
          onClick={() => go(-1)}
        >
          <ChevronLeft size={20} aria-hidden />
        </button>
        <h1 className="money-head__title">{monthTitle(`${shown}-01`, lang)}</h1>
        <button
          type="button"
          className="icon-button"
          aria-label={t.money.nextMonth}
          disabled={shown >= current}
          onClick={() => go(1)}
        >
          <ChevronRight size={20} aria-hidden />
        </button>
      </header>
      {month.isPending ? (
        <Loader />
      ) : month.isLoadingError ? (
        <ErrorState onRetry={() => void month.refetch()} />
      ) : (
        <MonthBody data={month.data} today={today} filter={filter} onFilter={setFilter} />
      )}
      <Fab href="/money/new" label={t.money.add} />
    </>
  );
}

function MonthBody({
  data, today, filter, onFilter,
}: { data: MoneyMonth; today: string; filter: number | null; onFilter: (id: number | null) => void }) {
  const categories: Categories = new Map(data.categories.map((category) => [category.id, category]));
  return (
    <>
      <Summary data={data} />
      <MoneyLinks />
      {data.spent > 0 && <ByCategory data={data} categories={categories} filter={filter} onFilter={onFilter} />}
      {data.spent > 0 && <ByDay data={data} today={today} />}
      <Entries data={data} categories={categories} today={today} filter={filter} onFilter={onFilter} />
      <RatesCard currency={data.currency} />
    </>
  );
}

/** USD, EUR and the user's currency, each with its last 30 days; a tap opens the rates. */
function RatesCard({ currency }: { currency: string }) {
  const t = useT();
  const rates = useRatesAll();
  const shown = (rates.data?.currencies ?? []).filter(
    (rate) => rate.code === "USD" || rate.code === "EUR" || rate.code === currency,
  );
  return (
    <Link href="/money/rates" className="card money-rates" style={{ "--i": 3 } as CSSProperties}>
      <span className="card__title">{t.money.rates}</span>
      {rates.isError ? (
        <span className="muted">{t.money.ratesUnavailable}</span>
      ) : (
        shown.map((rate) => <RateRow key={rate.code} rate={rate} />)
      )}
    </Link>
  );
}

function RateRow({ rate }: { rate: CurrencyRate }) {
  const lang = useLang();
  const history = useRateHistory(rate.code);
  return (
    <span className="rate-row">
      <span className="rate-row__code">{rate.code}</span>
      <span className="rate-row__value">{formatRate(rate.value, lang)}</span>
      <span className="muted rate-row__change">{rateChange(rate, lang)}</span>
      <Sparkline values={history.data?.points.map((point) => point.value) ?? []} />
    </span>
  );
}

/** The budget and the categories, each on its own screen. */
function MoneyLinks() {
  const t = useT();
  return (
    <div className="money-links">
      <Link href="/money/budget" className="chip-button">{t.money.budgetLink}</Link>
      <Link href="/money/categories" className="chip-button">{t.money.categoriesLink}</Link>
    </div>
  );
}

function Summary({ data }: { data: MoneyMonth }) {
  const t = useT();
  const lang = useLang();
  return (
    <Card index={0}>
      <p className="money-summary__label">{t.money.spent}</p>
      <p className="money-summary__spent">{formatAmount(data.spent, data.currency, lang)}</p>
      {data.budget !== null && data.left !== null && (
        <>
          <BudgetBar spent={data.spent} budget={data.budget} />
          <p className="money-summary__line muted">
            {budgetText(data.budget, data.left, data.per_day, data.currency, lang, t)}
          </p>
        </>
      )}
      {data.budget === null && (
        <Link href="/money/budget" className="money-summary__set">{t.money.setBudget}</Link>
      )}
      {data.income > 0 && (
        <p className="money-summary__line muted">
          {t.money.income(
            formatAmount(data.income, data.currency, lang),
            formatSigned(data.balance, data.currency, lang),
          )}
        </p>
      )}
    </Card>
  );
}

function ByCategory({
  data, categories, filter, onFilter,
}: { data: MoneyMonth; categories: Categories; filter: number | null; onFilter: (id: number | null) => void }) {
  const t = useT();
  const lang = useLang();
  const shares = data.expenses.map(
    (item) => `${categories.get(item.category_id)?.name ?? ""} ${percentText(item.share, lang)}`,
  );
  return (
    <Card title={t.money.byCategory} index={1}>
      <div className="money-ring">
        <Ring
          parts={ringParts(data.expenses)}
          label={t.money.ring(formatAmount(data.spent, data.currency, lang), shares.join(", "))}
          count={String(data.entries.length)}
          caption={t.money.entriesWord(data.entries.length)}
        />
      </div>
      <ul className="legend">
        {data.expenses.map((item, index) => {
          const category = categories.get(item.category_id);
          if (!category) return null;
          const pressed = filter === category.id;
          return (
            <li key={category.id}>
              <button
                type="button"
                className="legend__row"
                aria-pressed={pressed}
                onClick={() => onFilter(pressed ? null : category.id)}
              >
                <span className="legend__dot" style={{ background: sliceColor(index) }} aria-hidden />
                <span className="legend__name">{`${category.emoji} ${category.name}`}</span>
                <span className="legend__amount">{formatAmount(item.amount, data.currency, lang)}</span>
                <span className="legend__share">{percentText(item.share, lang)}</span>
              </button>
              {category.budget !== null && item.left !== null && (
                <div className="legend__budget">
                  <BudgetBar spent={item.amount} budget={category.budget} />
                  <span className="muted">{budgetText(category.budget, item.left, null, data.currency, lang, t)}</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function ByDay({ data, today }: { data: MoneyMonth; today: string }) {
  const t = useT();
  const lang = useLang();
  const most = data.days.reduce<number>((best, value, index) => ((value ?? 0) > (data.days[best] ?? 0) ? index : best), 0);
  const day = dayMonth(`${data.month}-${String(most + 1).padStart(2, "0")}`, lang);
  return (
    <Card title={t.money.byDay} index={2}>
      <DayBars
        days={data.days}
        today={monthOf(today) === data.month ? Number(today.slice(8)) : 0}
        label={t.money.days(day, formatAmount(data.days[most] ?? 0, data.currency, lang))}
      />
    </Card>
  );
}

function Entries({
  data, categories, today, filter, onFilter,
}: {
  data: MoneyMonth;
  categories: Categories;
  today: string;
  filter: number | null;
  onFilter: (id: number | null) => void;
}) {
  const t = useT();
  const lang = useLang();
  const remove = useDeleteEntry();
  const chosen = filter === null ? undefined : categories.get(filter);
  const entries = chosen ? data.entries.filter((entry) => entry.category_id === chosen.id) : data.entries;
  return (
    <section className="money-entries" aria-labelledby="money-entries">
      <div className="money-entries__head">
        <h2 id="money-entries" className="card__title">{t.money.entries}</h2>
        {chosen && (
          <button type="button" className="chip-button" aria-label={t.money.showAll(chosen.name)} onClick={() => onFilter(null)}>
            {`${chosen.emoji} ${chosen.name} ✕`}
          </button>
        )}
      </div>
      {entries.length === 0 && <Empty text={chosen ? t.money.emptyCategory : t.money.empty} />}
      {byDay(entries).map((group) => (
        <div key={group.day}>
          <h3 className="group__label">{entryDay(group.day, today, lang, t.calendar.words)}</h3>
          {group.entries.map((entry) => {
            const category = categories.get(entry.category_id);
            if (!category) return null;
            const income = category.kind === "income";
            return (
              <SwipeRow key={entry.id} onDelete={() => remove.mutate(entry.id)} deleteLabel={t.money.deleteEntry}>
                <Link href={`/money/${entry.id}/edit`} className="money-entry">
                  <span className="money-entry__emoji" aria-hidden>{category.emoji}</span>
                  <span className="money-entry__text">
                    <span className="money-entry__title">{entry.note || category.name}</span>
                    {entry.note && <span className="money-entry__sub">{category.name}</span>}
                  </span>
                  <span className={income ? "money-entry__amount money-entry__amount--income" : "money-entry__amount"}>
                    {formatAmount(entry.amount, data.currency, lang, income)}
                  </span>
                </Link>
              </SwipeRow>
            );
          })}
        </div>
      ))}
    </section>
  );
}
