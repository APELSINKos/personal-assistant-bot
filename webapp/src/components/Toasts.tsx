import { useT } from "../i18n";
import { useToasts } from "./toastStore";

export function Toasts() {
  const t = useT();
  const items = useToasts();
  const messages: Record<string, string> = t.errors;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast--${item.kind}`}>
          {item.text ?? messages[item.code ?? "generic"] ?? t.errors.generic}
        </div>
      ))}
    </div>
  );
}
