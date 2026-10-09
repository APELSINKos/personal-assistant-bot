/**
 * Dialogs inside the device (spec §4.3): the app's questions, the closing question, the bot's
 * permission and the chat picker, drawn where Telegram draws its own — over the app, inside the
 * phone. Each is modal: the rest of the page is inert while it is open, Tab keeps to its buttons,
 * Esc and a tap outside it cancel, and focus goes back where it was — into the app's frame when the
 * app asked.
 */
import { h } from "./dom";

export interface Choice<T> {
  text: string;
  value: T;
  primary?: boolean;
}

export interface DialogSpec<T> {
  /** A question in the middle of the screen, or a sheet from its bottom. */
  kind: "question" | "sheet";
  /** The question itself, or the sheet's heading: the dialog's name for screen readers. */
  label: string;
  /** What the dialog shows under its label. */
  content?: Node[];
  choices: Choice<T>[];
  /** What Esc and a tap outside the dialog answer. */
  cancel: T;
  /** The choice focused first, by its place; the first one by default. */
  focus?: number;
}

export interface Dialogs {
  /** The visitor's choice; refused while another dialog is open, as Telegram refuses a popup. */
  open<T>(spec: DialogSpec<T>): Promise<T>;
  isOpen(): boolean;
  /** Closes the open dialog, if any, with its cancel answer. */
  dismiss(): void;
}

interface Focusable {
  focus(options?: FocusOptions): void;
}

function canFocus(element: unknown): element is Focusable {
  return typeof (element as Focusable | null)?.focus === "function";
}

/** Where focus was when a dialog opened, and the way back to it. */
function rememberFocus(): () => boolean {
  const opener = document.activeElement;
  // Focus in the app's frame: the frame and, inside it, the element the visitor was on.
  const inner = opener instanceof HTMLIFrameElement ? opener.contentDocument?.activeElement : null;
  return () => {
    if (!(opener instanceof HTMLElement) || opener === document.body) return false;
    if (!opener.isConnected || opener.closest("[hidden]")) return false;
    opener.focus();
    if (canFocus(inner)) inner.focus({ preventScroll: true });
    return true;
  };
}

let count = 0;

/**
 * Dialogs in `layer`; `outside` names what turns inert while one is open, and `fallback` takes
 * focus when the element that had it is gone.
 */
export function createDialogs(layer: HTMLElement, outside: () => Element[], fallback: () => void): Dialogs {
  let close: ((cancelled: boolean, value?: unknown) => void) | null = null;

  layer.hidden = true;
  layer.addEventListener("click", (event) => {
    if (event.target === layer) close?.(true);
  });

  function open<T>(spec: DialogSpec<T>): Promise<T> {
    if (close) return Promise.reject(new Error("A dialog is open already"));
    count += 1;
    const labelId = `demo-dialog-${count}`;
    const label = spec.kind === "sheet" ? h("h2", { class: "dialog__title", id: labelId }, spec.label)
      : h("p", { class: "dialog__message", id: labelId }, spec.label);
    const buttons = spec.choices.map((choice) =>
      h("button", { type: "button", class: choice.primary ? "dialog__button dialog__button--primary" : "dialog__button" },
        choice.text));
    const box = h("div", {
      class: `dialog dialog--${spec.kind}`, role: "dialog", "aria-modal": "true", "aria-labelledby": labelId,
      tabindex: "-1",
    }, label, ...(spec.content ?? []), h("div", { class: "dialog__choices" }, ...buttons));

    const back = rememberFocus();
    const inert = outside();
    for (const element of inert) element.toggleAttribute("inert", true);
    layer.className = `tg-layer tg-layer--${spec.kind}`;
    layer.replaceChildren(box);
    layer.hidden = false;

    return new Promise<T>((resolve) => {
      const keys = (event: KeyboardEvent) => {
        if (event.key === "Escape") {
          event.preventDefault();
          finish(true);
        } else if (event.key === "Tab") {
          // Tab and Shift+Tab go round the dialog's buttons and never leave it.
          const first = buttons[0];
          const last = buttons[buttons.length - 1];
          const inside = box.contains(document.activeElement);
          if (event.shiftKey && (!inside || document.activeElement === first || document.activeElement === box)) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && (!inside || document.activeElement === last)) {
            event.preventDefault();
            first?.focus();
          }
        }
      };
      const finish = (cancelled: boolean, value?: unknown) => {
        document.removeEventListener("keydown", keys, true);
        close = null;
        layer.hidden = true;
        layer.replaceChildren();
        for (const element of inert) element.removeAttribute("inert");
        if (!back()) fallback();
        resolve(cancelled ? spec.cancel : (value as T));
      };
      close = finish;
      document.addEventListener("keydown", keys, true);
      spec.choices.forEach((choice, index) => {
        buttons[index]?.addEventListener("click", () => finish(false, choice.value));
      });
      buttons[spec.focus ?? 0]?.focus();
    });
  }

  return {
    open,
    isOpen: () => close !== null,
    dismiss: () => close?.(true),
  };
}
