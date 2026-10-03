import { useT } from "../i18n";

export function Loader() {
  const t = useT();
  return (
    <div role="status" aria-busy="true" aria-label={t.common.loading}>
      <div className="skeleton" />
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}

export function ErrorState({ onRetry, text }: { onRetry: () => void; text?: string }) {
  const t = useT();
  return (
    <div className="error-state" role="alert">
      <div>{text ?? t.errors.generic}</div>
      <button type="button" className="button" onClick={onRetry}>
        {t.common.retry}
      </button>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}
