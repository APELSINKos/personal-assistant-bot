import { useId } from "react";
import { useT } from "../i18n";

/**
 * An amount in the user's currency, the sign at the field's end; under it, why it cannot be saved.
 * `inline` puts the label and the field on one line.
 */
export function AmountField({
  label, value, sign, invalid, onChange, big = false, inline = false, placeholder = "0",
}: {
  label: string;
  value: string;
  sign: string;
  invalid: boolean;
  onChange: (value: string) => void;
  big?: boolean;
  inline?: boolean;
  placeholder?: string;
}) {
  const t = useT();
  const id = useId();
  return (
    <>
      <div className={inline ? "field field--inline" : "field"}>
        <label className="field__label" htmlFor={id}>{label}</label>
        <span className={big ? "money-amount money-amount--big" : "money-amount"}>
          <input
            id={id}
            className="input"
            inputMode="decimal"
            autoComplete="off"
            placeholder={placeholder}
            value={value}
            aria-invalid={invalid}
            aria-describedby={invalid ? `${id}-hint` : undefined}
            onChange={(event) => onChange(event.target.value)}
          />
          <span className="money-amount__sign" aria-hidden>{sign}</span>
        </span>
      </div>
      <div aria-live="polite">
        {invalid && <p className="field__hint" id={`${id}-hint`}>{t.money.amountHint}</p>}
      </div>
    </>
  );
}
