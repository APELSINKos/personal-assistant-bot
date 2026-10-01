import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangProvider } from "../i18n";
import { ErrorBoundary } from "./ErrorBoundary";
import { Toasts } from "./Toasts";
import { toast, type ToastInput } from "./toastStore";

const GENERIC = "Что-то пошло не так. Попробуй ещё раз.";

/** The toasts inside the app's own error boundary, next to something else on the page. */
function showToast(input: ToastInput) {
  render(
    <ErrorBoundary reload={() => undefined}>
      <LangProvider lang="ru">
        <p>the rest of the app</p>
        <Toasts />
      </LangProvider>
    </ErrorBoundary>,
  );
  act(() => {
    toast(input);
  });
}

describe("Toasts", () => {
  it("explains an error by its code", () => {
    showToast({ kind: "error", code: "not_found" });
    expect(screen.getByText("Этого уже нет")).toBeInTheDocument();
  });

  it("shows a given text as it is", () => {
    showToast({ kind: "success", text: "Готово" });
    expect(screen.getByText("Готово")).toBeInTheDocument();
  });

  it.each([undefined, "no_such_code"])("falls back to the generic text for the code %s", (code) => {
    showToast({ kind: "error", code });
    expect(screen.getByText(GENERIC)).toBeInTheDocument();
  });

  // A code can be a string the server sent: it must never be looked up among what every object has.
  it.each(["__proto__", "constructor", "toString", "hasOwnProperty"])(
    "shows the generic text, and the app keeps rendering, for the code %s",
    (code) => {
      showToast({ kind: "error", code });
      expect(screen.getByText(GENERIC)).toBeInTheDocument();
      expect(screen.getByText("the rest of the app")).toBeInTheDocument();
    },
  );
});
