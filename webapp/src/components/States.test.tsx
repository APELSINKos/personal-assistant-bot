import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LangProvider } from "../i18n";
import { Empty, ErrorState, Loader } from "./States";

function withLang(ui: React.ReactElement) {
  return <LangProvider lang="ru">{ui}</LangProvider>;
}

describe("States", () => {
  it("announces the loader through role=status so its aria-label is read out", () => {
    render(withLang(<Loader />));
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Загрузка…");
  });

  it("lets the user retry from an error state", () => {
    const onRetry = vi.fn();
    render(withLang(<ErrorState onRetry={onRetry} />));
    screen.getByRole("button", { name: "Повторить" }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the given empty-state text", () => {
    render(<Empty text="Ничего нет" />);
    expect(screen.getByText("Ничего нет")).toBeInTheDocument();
  });
});
