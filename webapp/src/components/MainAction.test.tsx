import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { MainAction } from "./MainAction";

describe("MainAction", () => {
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
