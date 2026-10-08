import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LangProvider } from "../i18n";
import { PullToRefresh } from "./PullToRefresh";

const at = (x: number, y: number) => ({ touches: [{ clientX: x, clientY: y }] });

function renderPull(onRefresh: () => Promise<unknown>) {
  render(
    <LangProvider lang="ru">
      <PullToRefresh onRefresh={onRefresh}>
        <p>Экран</p>
      </PullToRefresh>
    </LangProvider>,
  );
  return screen.getByText("Экран");
}

describe("PullToRefresh", () => {
  it("refreshes when pulled down far enough", async () => {
    const onRefresh = vi.fn(() => Promise.resolve());
    const body = renderPull(onRefresh);
    fireEvent.touchStart(body, at(100, 100));
    fireEvent.touchMove(body, at(104, 180));
    expect(screen.getByText("Потяни, чтобы обновить")).toBeInTheDocument();
    fireEvent.touchMove(body, at(104, 260)); // 160 px down: a pull of 80, past the 64 it takes
    fireEvent.touchEnd(body);
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(screen.getByText("Обновляю…")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Обновляю…")).not.toBeInTheDocument());
  });

  it("does not refresh on a short pull", () => {
    const onRefresh = vi.fn(() => Promise.resolve());
    const body = renderPull(onRefresh);
    fireEvent.touchStart(body, at(100, 100));
    fireEvent.touchMove(body, at(100, 200)); // a pull of 50
    fireEvent.touchEnd(body);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("takes a sideways swipe for no pull, however far it drifts down", () => {
    const onRefresh = vi.fn(() => Promise.resolve());
    const body = renderPull(onRefresh);
    fireEvent.touchStart(body, at(200, 100));
    fireEvent.touchMove(body, at(120, 110)); // the 24-hour strip scrolls
    fireEvent.touchMove(body, at(60, 300));
    expect(screen.queryByText("Потяни, чтобы обновить")).not.toBeInTheDocument();
    fireEvent.touchEnd(body);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
