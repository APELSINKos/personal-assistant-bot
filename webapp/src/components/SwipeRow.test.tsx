import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { stubPointer } from "../test/pointer";
import { SwipeRow } from "./SwipeRow";

function touch(clientX: number, clientY = 0) {
  return { touches: [{ clientX, clientY }] };
}

/** An entry's row as the money list has it: a link, then its own delete button. */
function entryRow(onDelete: () => void) {
  render(
    <SwipeRow onDelete={onDelete} deleteLabel="Удалить запись «кофе», 430 ₽" question="Удалить запись?">
      <a href="/money/24/edit">кофе</a>
    </SwipeRow>,
  );
  return screen.getByRole("button", { name: "Удалить запись «кофе», 430 ₽" });
}

describe("SwipeRow", () => {
  it("puts the delete button after the row's content, so Tab reaches the row first", () => {
    const button = entryRow(vi.fn());
    const link = screen.getByRole("link", { name: "кофе" });
    expect(link.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("with a mouse, asks its question first and deletes nothing on «Отмена»", async () => {
    stubPointer("mouse");
    const app = installTelegram({
      showConfirm: vi.fn((_message: string, callback: (ok: boolean) => void) => callback(false)),
    });
    const onDelete = vi.fn();
    fireEvent.click(entryRow(onDelete));
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить запись?", expect.any(Function));
    // Time enough for a deletion that should not happen to go through.
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("with a mouse, deletes once answered yes", async () => {
    stubPointer("mouse");
    const app = installTelegram();
    const onDelete = vi.fn();
    fireEvent.click(entryRow(onDelete));
    await waitFor(() => expect(onDelete).toHaveBeenCalledTimes(1));
    expect(app.showConfirm).toHaveBeenCalledWith("Удалить запись?", expect.any(Function));
  });

  it("on a phone, deletes at once: the swipe that showed the button was the first step", () => {
    stubPointer("touch");
    const app = installTelegram();
    const onDelete = vi.fn();
    fireEvent.click(entryRow(onDelete));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(app.showConfirm).not.toHaveBeenCalled();
  });

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
