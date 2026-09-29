import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { ErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("broken render");
}

describe("ErrorBoundary", () => {
  it("shows the error state instead of a blank page and reloads on retry", () => {
    const report = vi.spyOn(console, "error").mockImplementation(() => undefined);
    installTelegram(); // language_code "ru"; no LangProvider around the boundary
    const reload = vi.fn();
    render(
      <ErrorBoundary reload={reload}>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Что-то пошло не так");
    screen.getByRole("button", { name: "Повторить" }).click();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalled(); // React still reports the error it caught
  });

  it("speaks the browser's language outside Telegram", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders its children when nothing fails", () => {
    render(
      <ErrorBoundary>
        <p>fine</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("fine")).toBeInTheDocument();
  });
});
