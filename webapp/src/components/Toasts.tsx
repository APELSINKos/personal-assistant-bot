import { errorText, useT } from "../i18n";
import { useToasts } from "./toastStore";

export function Toasts() {
  const t = useT();
  const items = useToasts();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast--${item.kind}`}>
          {item.text ?? errorText(t, item.code)}
        </div>
      ))}
    </div>
  );
}
