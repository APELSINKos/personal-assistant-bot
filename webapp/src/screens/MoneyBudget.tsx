import { useState } from "react";
import { useLocation } from "wouter";
import { useMoneyCategories, useSetBudget, useUpdateCategory } from "../api/money";
import { useMe } from "../api/queries";
import type { MoneyCategory } from "../api/types";
import { AmountField } from "../components/AmountField";
import { BackTo } from "../components/BackTo";
import { Card } from "../components/Card";
import { MainAction } from "../components/MainAction";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT } from "../i18n";
import { amountText, currencySign, parseAmount } from "../lib/money";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const TOTAL = "total";
const field = (category: MoneyCategory) => `category-${category.id}`;

/** The month's budgets: the total one and each expense category's; an empty field means none. */
export function MoneyBudget() {
  const me = useMe();
  const categories = useMoneyCategories();
  if (me.isError || categories.isError) {
    return (
      <BackTo href="/money">
        <ErrorState onRetry={() => void Promise.all([me.refetch(), categories.refetch()])} />
      </BackTo>
    );
  }
  if (me.isPending || categories.isPending) {
    return (
      <BackTo href="/money">
        <Loader />
      </BackTo>
    );
  }
  // A hidden category is listed only while it still has a budget, so that it can be taken off.
  const expenses = categories.data.filter(
    (category) => category.kind === "expense" && (!category.hidden || category.budget !== null),
  );
  return <BudgetEditor total={me.data.money_budget} categories={expenses} currency={me.data.currency} />;
}

function BudgetEditor({
  total, categories, currency,
}: { total: number | null; categories: MoneyCategory[]; currency: string }) {
  const t = useT();
  const lang = useLang();
  const [, navigate] = useLocation();
  const setBudget = useSetBudget();
  const updateCategory = useUpdateCategory();
  const [initial] = useState<Record<string, string>>(() => {
    const text = (amount: number | null) => (amount === null ? "" : amountText(amount, lang));
    const fields: Record<string, string> = { [TOTAL]: text(total) };
    for (const category of categories) fields[field(category)] = text(category.budget);
    return fields;
  });
  const [fields, setFields] = useState(initial);
  const value = (key: string) => (fields[key] ?? "").trim();
  const wrong = (key: string) => value(key) !== "" && parseAmount(value(key)) === null;
  const keys = Object.keys(fields);
  const changed = keys.filter((key) => fields[key] !== initial[key]);
  const valid = !keys.some(wrong);
  const busy = setBudget.isPending || updateCategory.isPending;

  useClosingConfirmation(changed.length > 0);
  useBackButton(() => {
    void (async () => {
      if (changed.length === 0 || (await confirmAction(t.notes.confirmDiscard))) navigate("/money");
    })();
  });

  const save = async () => {
    if (!valid || busy) return;
    const amount = (key: string) => (value(key) === "" ? null : parseAmount(value(key)));
    try {
      for (const key of changed) {
        if (key === TOTAL) await setBudget.mutateAsync(amount(key));
        else await updateCategory.mutateAsync({ id: Number(key.slice("category-".length)), patch: { budget: amount(key) } });
      }
      navigate("/money");
    } catch {
      // The toast has said what went wrong; the fields keep what was typed.
    }
  };
  const input = (key: string, label: string, inline = false) => (
    <AmountField
      key={key}
      inline={inline}
      label={label}
      value={fields[key] ?? ""}
      sign={currencySign(currency)}
      placeholder={t.money.noBudget}
      invalid={wrong(key)}
      onChange={(text) => setFields({ ...fields, [key]: text })}
    />
  );

  return (
    <>
      <h1 className="screen__title">{t.money.budgetTitle}</h1>
      <p className="muted money-form__hint">{t.money.budgetHint}</p>
      <Card index={0}>{input(TOTAL, t.money.budgetTotal)}</Card>
      <Card title={t.money.budgetCategories} index={1}>
        {categories.map((category) => input(field(category), `${category.emoji} ${category.name}`, true))}
      </Card>
      <MainAction text={t.common.save} onClick={() => void save()} disabled={!valid} busy={busy} />
    </>
  );
}
