import { useEffect, useRef } from "react";
import { webApp } from "../telegram";

interface Props {
  text: string;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
}

/** Telegram's bottom main button inside Telegram; an ordinary sticky button elsewhere. */
export function MainAction({ text, onClick, disabled = false, busy = false }: Props) {
  const app = webApp();
  const latest = useRef(onClick);
  useEffect(() => {
    latest.current = onClick;
  });

  useEffect(() => {
    if (!app) return;
    const click = () => latest.current();
    app.MainButton.onClick(click);
    return () => {
      app.MainButton.offClick(click);
      app.MainButton.hideProgress?.();
      app.MainButton.hide();
    };
  }, [app]);

  useEffect(() => {
    if (!app) return;
    // The progress first: telegram-web-app.js makes the button active again when its progress
    // ends, so the button's state goes after it.
    if (busy) app.MainButton.showProgress?.(false);
    else app.MainButton.hideProgress?.();
    app.MainButton.setParams({ text, is_active: !disabled && !busy, is_visible: true });
  }, [app, text, disabled, busy]);

  if (app) return null;
  return (
    <div className="main-action">
      <button type="button" className="button button--primary" onClick={onClick} disabled={disabled || busy}>
        {text}
      </button>
    </div>
  );
}
