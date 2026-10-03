import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import { ApiError } from "../api/client";
import { useDeleteEntry, useMoneyCategories, useMoneyEntry, useSaveEntry } from "../api/money";
import { useMe } from "../api/queries";
import type { MoneyCategory, MoneyEntry, MoneyEntryInput, MoneyKind } from "../api/types";
import { AmountField } from "../components/AmountField";
import { BackTo } from "../components/BackTo";
import { MainAction } from "../components/MainAction";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT } from "../i18n";
import { addDaysIso, localTodayIso } from "../lib/format";
import { amountText, currencySign, ENTRY_DAYS_BACK, parseAmount } from "../lib/money";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_NOTE = 100;
const KINDS: MoneyKind[] = ["expense", "income"];

interface Draft {
  amount: string;
  kind: MoneyKind;
  category: number | null;
  note: string;
  day: string;
}

interface EditorProps {
  today: string;
  categories: MoneyCategory[];
  currency: string;
}

/** A new entry (/money/new) or an existing one (/money/:id/edit). */
export function MoneyEntryForm() {
  const [, params] = useRoute<{ id: string }>("/money/:id/edit");
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
  const props = { today: localTodayIso(me.data.city.timezone), categories: categories.data, currency: me.data.currency };
  return params ? <EditEntry id={Number(params.id)} {...props} /> : <EntryEditor {...props} />;
}

function EditEntry({ id, ...props }: { id: number } & EditorProps) {
  const t = useT();
  const entry = useMoneyEntry(id);
  if (entry.isPending) {
    return (
      <BackTo href="/money">
        <Loader />
      </BackTo>
    );
  }
  if (entry.isError) {
    return (
      <BackTo href="/money">
        {entry.error instanceof ApiError && entry.error.status === 404 ? (
          <div className="empty">
            <p>{t.money.gone}</p>
            <Link href="/money" className="button">{t.money.toMoney}</Link>
          </div>
        ) : (
          <ErrorState onRetry={() => void entry.refetch()} />
        )}
      </BackTo>
    );
  }
  return <EntryEditor entry={entry.data} {...props} />;
}

function EntryEditor({ entry, today, categories, currency }: EditorProps & { entry?: MoneyEntry }) {
  const t = useT();
  const lang = useLang();
  const [, navigate] = useLocation();
  const save = useSaveEntry();
  const remove = useDeleteEntry();
  const kindOf = (id: number | null) => categories.find((category) => category.id === id)?.kind;
  const [initial] = useState<Draft>(() =>
    entry
      ? {
          amount: amountText(entry.amount, lang),
          kind: kindOf(entry.category_id) ?? "expense",
          category: entry.category_id,
          note: entry.note,
          day: entry.day,
        }
      : { amount: "", kind: "expense", category: null, note: "", day: today },
  );
  const [draft, setDraft] = useState(initial);
  const change = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });

  const amount = parseAmount(draft.amount);
  const oldest = addDaysIso(today, -ENTRY_DAYS_BACK);
  // An entry keeps its own day even once that is further back than a new day may be.
  const dayValid = draft.day === initial.day || (draft.day >= oldest && draft.day <= today);
  const valid = amount !== null && draft.category !== null && dayValid;
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  // A hidden category is not offered, unless it is the entry's own.
  const offered = categories.filter(
    (category) => category.kind === draft.kind && (!category.hidden || category.id === draft.category),
  );

  useClosingConfirmation(dirty);
  useBackButton(() => {
    void (async () => {
      if (!dirty || (await confirmAction(t.notes.confirmDiscard))) navigate("/money");
    })();
  });

  const submit = () => {
    if (!valid || save.isPending || amount === null || draft.category === null) return;
    const fields: MoneyEntryInput = { amount, category_id: draft.category, note: draft.note.trim(), day: draft.day };
    const done = { onSuccess: () => navigate("/money") };
    if (!entry) save.mutate({ entry: fields }, done);
    else save.mutate({ id: entry.id, entry: draft.day === entry.day ? { ...fields, day: undefined } : fields }, done);
  };
  const onDelete = async () => {
    if (!entry || !(await confirmAction(t.money.confirmDelete))) return;
    remove.mutate(entry.id);
    navigate("/money");
  };

  return (
    <>
      <h1 className="screen__title">{entry ? t.money.editEntry : t.money.newEntry}</h1>
      <AmountField
        big
        label={t.money.amount}
        value={draft.amount}
        sign={currencySign(currency)}
        invalid={draft.amount.trim() !== "" && amount === null}
        onChange={(value) => change({ amount: value })}
      />

      <div className="field">
        <div className="segmented money-kinds" role="group" aria-label={t.money.kind}>
          {KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              className="segmented__option"
              aria-pressed={draft.kind === kind}
              onClick={() => change({ kind, category: kindOf(draft.category) === kind ? draft.category : null })}
            >
              {t.money.kinds[kind]}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label" id="money-category">{t.money.category}</span>
        <div className="category-grid" role="group" aria-labelledby="money-category">
          {offered.map((category) => (
            <button
              key={category.id}
              type="button"
              className="category-grid__item"
              aria-pressed={draft.category === category.id}
              onClick={() => change({ category: category.id })}
            >
              <span className="category-grid__emoji" aria-hidden>{category.emoji}</span>
              <span className="category-grid__name">{category.name}</span>
            </button>
          ))}
        </div>
      </div>

      <label className="field">
        <span className="field__label">{t.money.note}</span>
        <input
          className="input"
          maxLength={MAX_NOTE}
          placeholder={t.money.notePlaceholder}
          value={draft.note}
          onChange={(event) => change({ note: event.target.value })}
        />
      </label>

      <div className="field">
        <span className="field__label" id="money-day">{t.money.day}</span>
        <div className="money-day">
          <button
            type="button"
            className="icon-button"
            aria-label={t.money.prevDay}
            disabled={draft.day <= oldest}
            onClick={() => change({ day: addDaysIso(draft.day, -1) })}
          >
            <ChevronLeft size={20} aria-hidden />
          </button>
          <input
            className="input"
            type="date"
            aria-labelledby="money-day"
            min={oldest}
            max={today}
            value={draft.day}
            onChange={(event) => {
              if (event.target.value) change({ day: event.target.value });
            }}
          />
          <button
            type="button"
            className="icon-button"
            aria-label={t.money.nextDay}
            disabled={draft.day >= today}
            onClick={() => change({ day: addDaysIso(draft.day, 1) })}
          >
            <ChevronRight size={20} aria-hidden />
          </button>
        </div>
      </div>
      <div aria-live="polite">{!dayValid && <p className="field__hint">{t.money.dayHint}</p>}</div>

      {entry && (
        <button type="button" className="button button--danger money-form__delete" onClick={() => void onDelete()}>
          {t.money.deleteEntry}
        </button>
      )}
      <MainAction text={t.common.save} onClick={submit} disabled={!valid} busy={save.isPending} />
    </>
  );
}
