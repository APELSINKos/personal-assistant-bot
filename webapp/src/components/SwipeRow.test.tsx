import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SwipeRow } from "./SwipeRow";

function touch(clientX: number, clientY = 0) {
  return { touches: [{ clientX, clientY }] };
}

describe("SwipeRow", () => {
  it("marks itself closed at rest, so the delete button stays hidden behind the row", () => {
    const { container } = render(
      <SwipeRow onDelete={vi.fn()} deleteLabel="Удалить">
        content
      </SwipeRow>,
    );
    expect(container.querySelector(".swipe")).toHaveAttribute("data-open", "false");
  });

  it("marks itself open once swiped past the threshold, revealing the delete button", () => {
    const { container } = render(
      <SwipeRow onDelete={vi.fn()} deleteLabel="Удалить">
        content
      </SwipeRow>,
    );
    const content = container.querySelector(".swipe__content") as Element;

    fireEvent.touchStart(content, touch(200));
    fireEvent.touchMove(content, touch(80)); // dx = -120, past the -88 open threshold
    fireEvent.touchEnd(content);

    expect(container.querySelector(".swipe")).toHaveAttribute("data-open", "true");
  });

  it("snaps back closed on a short swipe", () => {
    const { container } = render(
      <SwipeRow onDelete={vi.fn()} deleteLabel="Удалить">
        content
      </SwipeRow>,
    );
    const content = container.querySelector(".swipe__content") as Element;

    fireEvent.touchStart(content, touch(200));
    fireEvent.touchMove(content, touch(180)); // dx = -20, short of the threshold
    fireEvent.touchEnd(content);

    expect(container.querySelector(".swipe")).toHaveAttribute("data-open", "false");
  });
});
