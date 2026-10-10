import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installTelegram, scriptMainButton } from "../test/fakeTelegram";
import { MainAction } from "./MainAction";

describe("MainAction", () => {
  it("leaves Telegram's main button inactive while the form cannot be saved", () => {
    const telegram = scriptMainButton();
    installTelegram({ MainButton: telegram.mainButton });
    const onClick = vi.fn();
    const { rerender } = render(<MainAction text="Сохранить" onClick={onClick} disabled />);

    expect(telegram.shown).toEqual({ text: "Сохранить", visible: true, active: false, progress: false });
    telegram.press();
    expect(onClick).not.toHaveBeenCalled();

    rerender(<MainAction text="Сохранить" onClick={onClick} />);
    expect(telegram.shown).toEqual({ text: "Сохранить", visible: true, active: true, progress: false });
    telegram.press();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("shows the progress of a save on an inactive button, and the form's state after it", () => {
    const telegram = scriptMainButton();
    installTelegram({ MainButton: telegram.mainButton });
    const { rerender } = render(<MainAction text="Сохранить" onClick={vi.fn()} busy />);
    expect(telegram.shown).toMatchObject({ active: false, progress: true });

    // The save failed, and the form cannot be saved as it is now.
    rerender(<MainAction text="Сохранить" onClick={vi.fn()} disabled />);
    expect(telegram.shown).toMatchObject({ active: false, progress: false });

    rerender(<MainAction text="Сохранить" onClick={vi.fn()} busy />);
    rerender(<MainAction text="Сохранить" onClick={vi.fn()} />);
    expect(telegram.shown).toMatchObject({ active: true, progress: false });
  });

  it("hides Telegram's main button and removes its click handler on unmount", () => {
    const app = installTelegram();
    const onClick = vi.fn();
    const { unmount } = render(<MainAction text="Сохранить" onClick={onClick} />);

    expect(app.MainButton.onClick).toHaveBeenCalledTimes(1);
    const registered = vi.mocked(app.MainButton.onClick).mock.calls[0]?.[0];

    unmount();

    expect(app.MainButton.offClick).toHaveBeenCalledWith(registered);
    expect(app.MainButton.hide).toHaveBeenCalledTimes(1);
  });

  it("renders its own sticky button outside Telegram instead", () => {
    const onClick = vi.fn();
    const { getByRole } = render(<MainAction text="Сохранить" onClick={onClick} />);
    getByRole("button", { name: "Сохранить" }).click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
