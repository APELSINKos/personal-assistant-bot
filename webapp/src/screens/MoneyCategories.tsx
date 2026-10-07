import { useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import { useCreateCategory, useMoneyCategories, useUpdateCategory } from "../api/money";
import type { MoneyCategory, MoneyCategoryPatch, MoneyKind } from "../api/types";
import { BackTo } from "../components/BackTo";
import { Card } from "../components/Card";
import { Fab } from "../components/Fab";
import { MainAction } from "../components/MainAction";
import { ErrorState, Loader } from "../components/States";
import { useTextLimit } from "../components/TextLimit";
import { useT } from "../i18n";
import { CATEGORY_EMOJI, CATEGORY_LIMIT } from "../lib/money";
import { confirmAction, useBackButton, useClosingConfirmation } from "../telegram";

const MAX_NAME = 30;
const KINDS: MoneyKind[] = ["expense", "income"];

/** Every category, the hidden ones too; a tap opens one. */
export function MoneyCategories() {
  const t = useT();
  const categories = useMoneyCategories();
  if (categories.isPending) return <Loader />;
  if (categories.isLoadingError) return <ErrorState onRetry={() => void categories.refetch()} />;
  return (
    <>
      <h1 className="screen__title">{t.money.categoriesTitle}</h1>
      {KINDS.map((kind, index) => (
        <Card key={kind} title={t.money.kindsPlural[kind]} index={index}>
          <ul className="list">
            {categories.data
              .filter((category) => category.kind === kind)
              .map((category) => (
                <li key={category.id}>
                  <Link
                    href={`/money/categories/${category.id}`}
                    className={category.hidden ? "category-row category-row--hidden" : "category-row"}
                  >
                    <span className="category-row__emoji" aria-hidden>{category.emoji}</span>
                    <span className="category-row__name">{category.name}</span>
                    {category.hidden && <span className="category-row__mark">{t.money.hiddenMark}</span>}
                    <span aria-hidden>›</span>
                  </Link>
                </li>
              ))}
          </ul>
        </Card>
      ))}
      {categories.data.length >= CATEGORY_LIMIT ? (
        <p className="muted">{t.money.categoriesFull(CATEGORY_LIMIT)}</p>
      ) : (
        <Fab href="/money/categories/new" label={t.money.newCategory} />
      )}
    </>
  );
}

/** A new category (/money/categories/new) or an existing one's name, emoji and visibility. */
export function MoneyCategoryForm() {
  const t = useT();
  const [isNew] = useRoute("/money/categories/new");
  const [, params] = useRoute<{ id: string }>("/money/categories/:id");
  const categories = useMoneyCategories();
  if (categories.isLoadingError) {
    return (
      <BackTo href="/money/categories">
        <ErrorState onRetry={() => void categories.refetch()} />
      </BackTo>
    );
  }
  if (categories.isPending) {
    return (
      <BackTo href="/money/categories">
        <Loader />
      </BackTo>
    );
  }
  if (isNew || !params) return <CategoryEditor />;
  const category = categories.data.find((item) => item.id === Number(params.id));
  if (!category) {
    return (
      <BackTo href="/money/categories">
        <div className="empty">
          <p>{t.money.categoryGone}</p>
          <Link href="/money/categories" className="button">{t.money.toCategories}</Link>
        </div>
      </BackTo>
    );
  }
  return <CategoryEditor category={category} />;
}

function CategoryEditor({ category }: { category?: MoneyCategory }) {
  const t = useT();
  const [, navigate] = useLocation();
  const create = useCreateCategory();
  const update = useUpdateCategory();
  const [initial] = useState(() => ({
    kind: category?.kind ?? ("expense" as MoneyKind),
    name: category?.name ?? "",
    emoji: category?.emoji ?? "🧾",
    hidden: category?.hidden ?? false,
  }));
  const [draft, setDraft] = useState(initial);
  const change = (patch: Partial<typeof initial>) => setDraft({ ...draft, ...patch });
  const name = draft.name.trim();
  const nameLimit = useTextLimit(name, MAX_NAME);
  const valid = name !== "" && !nameLimit.over;
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  const busy = create.isPending || update.isPending;

  useClosingConfirmation(dirty);
  useBackButton(() => {
    void (async () => {
      if (!dirty || (await confirmAction(t.notes.confirmDiscard))) navigate("/money/categories");
    })();
  });

  const save = () => {
    if (!valid || busy) return;
    const done = { onSuccess: () => navigate("/money/categories") };
    if (!category) {
      create.mutate({ kind: draft.kind, name, emoji: draft.emoji }, done);
      return;
    }
    const patch: MoneyCategoryPatch = {};
    if (name !== category.name) patch.name = name;
    if (draft.emoji !== category.emoji) patch.emoji = draft.emoji;
    if (draft.hidden !== category.hidden) patch.hidden = draft.hidden;
    update.mutate({ id: category.id, patch }, done);
  };

  return (
    <>
      <h1 className="screen__title">{category ? t.money.categoryTitle : t.money.newCategory}</h1>
      {!category && (
        <div className="field">
          <div className="segmented money-kinds" role="group" aria-label={t.money.kind}>
            {KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                className="segmented__option"
                aria-pressed={draft.kind === kind}
                onClick={() => change({ kind })}
              >
                {t.money.kinds[kind]}
              </button>
            ))}
          </div>
        </div>
      )}
      <label className="field">
        <span className="field__label">{t.money.name}</span>
        <input className="input" value={draft.name} {...nameLimit.field} onChange={(event) => change({ name: event.target.value })} />
      </label>
      {nameLimit.hint}
      <div className="field">
        <span className="field__label" id="category-emoji">{t.money.emoji}</span>
        <div className="emoji-grid category-emoji" role="group" aria-labelledby="category-emoji">
          {CATEGORY_EMOJI.map((emoji) => (
            <button
              key={emoji}
              type="button"
              className="emoji-grid__item"
              aria-pressed={draft.emoji === emoji}
              onClick={() => change({ emoji })}
            >
              {emoji}
            </button>
          ))}
        </div>
      </div>
      {category &&
        (category.can_hide ? (
          <div className="field">
            <label className="switch-row row">
              <span>{t.money.hide}</span>
              <input
                type="checkbox"
                role="switch"
                className="switch"
                checked={draft.hidden}
                onChange={(event) => change({ hidden: event.target.checked })}
              />
            </label>
            <p className="muted field__note">{t.money.hideHint}</p>
          </div>
        ) : (
          <p className="muted field__note">{t.money.otherFixed}</p>
        ))}
      <MainAction text={t.common.save} onClick={save} disabled={!valid} busy={busy} />
    </>
  );
}
