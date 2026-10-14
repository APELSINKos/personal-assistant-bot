import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Lang } from "../../i18n";
import type { DemoFrame } from "../bridge/contract";
import { createDevice } from "./device";
import { WORDS } from "./words";

/** What the app's frame says to the host. */
function appSide(): DemoFrame {
  return { mainButtonClicked: vi.fn(), backButtonClicked: vi.fn(), themeChanged: vi.fn() };
}

/**
 * The device on a page of its own, with the app's frame connected. `loads` lists the addresses loaded
 * into the frame after the first, each «assign» (a step of the history) or «replace» (in place of the
 * frame's document): jsdom loads none.
 */
function stand(language: Lang = "ru") {
  const loads: string[] = [];
  const device = createDevice({
    language: () => language, words: () => WORDS[language],
    load: (_frame, address, replace) => loads.push(`${replace ? "replace" : "assign"} ${address}`),
  });
  document.body.append(device.element);
  device.open("/");
  const frame = appSide();
  device.chrome.connect(frame);
  return { device, frame, loads };
}

function appFrame(): HTMLIFrameElement {
  const frame = document.querySelector("iframe");
  if (!frame) throw new Error("No frame of the app");
  return frame;
}

function press(key: string, options: { shiftKey?: boolean } = {}): void {
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...options });
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("the demo's device", () => {
  it("holds the app in a frame named for screen readers, under a header that says it is a demo", () => {
    stand();
    expect(appFrame()).toHaveAttribute("title", "Приложение «Личный помощник»");
    expect(appFrame().getAttribute("src")).toBe("./app.html#/");
    const header = within(document.querySelector("header") as HTMLElement);
    expect(header.getByText("Личный помощник")).toBeInTheDocument();
    expect(header.getByText("демо")).toBeInTheDocument();
  });

  it("speaks the visitor's language", () => {
    stand("en");
    expect(appFrame()).toHaveAttribute("title", "The Personal Assistant app");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.getByText("Personal Assistant")).toBeInTheDocument();
  });

  it("shows the loading screen until the app is ready", () => {
    const { device } = stand();
    expect(screen.getByText("Приложение загружается")).toBeVisible();
    device.chrome.ready();
    expect(screen.getByText("Приложение загружается")).not.toBeVisible();
  });

  it("paints the header, the background and the bar under the app", () => {
    const { device } = stand();
    device.chrome.paint("header", "#f7f5f2");
    device.chrome.paint("background", "#0a0913");
    device.chrome.paint("bottom", "#123456");
    expect((document.querySelector(".tg-top") as HTMLElement).style.backgroundColor).toBe("rgb(247, 245, 242)");
    expect((document.querySelector(".tg-view") as HTMLElement).style.backgroundColor).toBe("rgb(10, 9, 19)");
    expect((document.querySelector(".tg-bottom") as HTMLElement).style.backgroundColor).toBe("rgb(18, 52, 86)");
  });

  it("turns «✕ Закрыть» into «‹ Назад» while the app shows its back button", () => {
    const { device, frame } = stand();
    const left = screen.getByRole("button", { name: "Закрыть" });
    expect(left.querySelector(".icon--close")).not.toBeNull();
    device.chrome.backButton(true);
    expect(left).toHaveAccessibleName("Назад");
    expect(left.querySelector(".icon--back")).not.toBeNull();
    left.click();
    expect(frame.backButtonClicked).toHaveBeenCalledOnce();
    device.chrome.backButton(false);
    expect(left).toHaveAccessibleName("Закрыть");
  });

  it("draws the main button under the app: its text, inactive, busy, gone", () => {
    const { device, frame } = stand();
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: false, progress: false });
    const save = screen.getByRole("button", { name: "Сохранить" });
    expect(save).toHaveAttribute("aria-disabled", "true");
    save.click();
    expect(frame.mainButtonClicked).not.toHaveBeenCalled();

    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    expect(save).toHaveAttribute("aria-disabled", "false");
    save.click();
    expect(frame.mainButtonClicked).toHaveBeenCalledOnce();

    device.chrome.mainButton({ text: "Сохранить", visible: true, active: false, progress: true });
    expect(save).toHaveAttribute("aria-busy", "true");
    expect(save.querySelector(".tg-main__spinner")).not.toHaveAttribute("hidden");

    device.chrome.mainButton({ text: "Сохранить", visible: false, active: true, progress: false });
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
  });

  it("leaves focus in the app when the main button it was on goes away", () => {
    const { device } = stand();
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    screen.getByRole("button", { name: "Сохранить" }).focus();
    device.chrome.mainButton({ text: "Сохранить", visible: false, active: true, progress: false });
    expect(appFrame()).toHaveFocus();
  });

  it("asks the app's question in a dialog inside the device and gives focus back to the app", async () => {
    const { device } = stand();
    appFrame().focus();
    const answer = device.chrome.confirm("Удалить заметку?");
    const dialog = screen.getByRole("dialog", { name: "Удалить заметку?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // A question is all in its name: nothing under it to describe.
    expect(dialog).not.toHaveAttribute("aria-describedby");
    expect(within(dialog).getByRole("button", { name: "Отмена" })).toHaveFocus();
    for (const part of [".tg-top", ".tg-view", ".tg-bottom"]) {
      expect(document.querySelector(part)).toHaveAttribute("inert");
    }
    within(dialog).getByRole("button", { name: "OK" }).click();
    await expect(answer).resolves.toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector("[inert]")).toBeNull();
    expect(appFrame()).toHaveFocus();
  });

  it("answers no to Esc and to a tap outside the question", async () => {
    const { device } = stand();
    const escaped = device.chrome.confirm("Удалить заметку?");
    press("Escape");
    await expect(escaped).resolves.toBe(false);
    const outside = device.chrome.confirm("Удалить заметку?");
    (document.querySelector(".tg-layer") as HTMLElement).click();
    await expect(outside).resolves.toBe(false);
  });

  it("keeps Tab inside the dialog", () => {
    const { device } = stand();
    void device.chrome.confirm("Удалить заметку?");
    const cancel = screen.getByRole("button", { name: "Отмена" });
    const ok = screen.getByRole("button", { name: "OK" });
    press("Tab", { shiftKey: true });
    expect(ok).toHaveFocus();
    press("Tab");
    expect(cancel).toHaveFocus();
  });

  it("refuses a second dialog while one is open, as Telegram refuses a popup", async () => {
    const { device } = stand();
    void device.chrome.confirm("Удалить заметку?");
    await expect(device.chrome.confirm("Удалить привычку?")).rejects.toThrow();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("asks before closing an app with unsaved changes", async () => {
    const { device } = stand();
    device.chrome.closingConfirmation(true);
    // From the keyboard: the button has focus when it is pressed.
    screen.getByRole("button", { name: "Закрыть" }).focus();
    screen.getByRole("button", { name: "Закрыть" }).click();
    const dialog = screen.getByRole("dialog", { name: "Изменения могут не сохраниться." });
    within(dialog).getByRole("button", { name: "Отмена" }).click();
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(appFrame()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Закрыть" })).toHaveFocus();

    screen.getByRole("button", { name: "Закрыть" }).click();
    within(screen.getByRole("dialog")).getByRole("button", { name: "Всё равно закрыть" }).click();
    await vi.waitFor(() => expect(screen.getByText("Приложение закрыто")).toBeVisible());
    expect(appFrame()).not.toBeVisible();
  });

  it("closes at once without the question, and opens the app again on «Сегодня»", () => {
    const { device, loads } = stand();
    const running = appFrame();
    running.dispatchEvent(new Event("load"));
    device.go("/habits");
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    device.chrome.backButton(false);
    screen.getByRole("button", { name: "Закрыть" }).click();
    expect(screen.getByText("Приложение закрыто")).toBeVisible();
    expect(running).not.toBeVisible();
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Закрыть" })).toBeNull();
    expect(screen.getByRole("link", { name: "Открыть бота в Telegram" })).toHaveAttribute(
      "href", "https://t.me/ikbo63_24_bot",
    );
    expect(screen.getByRole("link", { name: "Исходный код на GitHub" })).toHaveAttribute(
      "href", "https://github.com/APELSINKos/personal-assistant-bot",
    );
    const again = screen.getByRole("button", { name: "Открыть снова" });
    expect(again).toHaveFocus();

    again.click();
    // A new start in the same frame, after the last one in the tab's history: Back goes to «Привычки».
    expect(appFrame()).toBe(running);
    expect(loads).toEqual(["assign ./app.html?start=1#/"]);
    expect(running).toBeVisible();
    expect(running).toHaveFocus();
    expect(screen.getByText("Приложение закрыто")).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeInTheDocument();
    expect(device.frame()).toBeNull();
  });

  it("keeps a closed app as it was: Back or Forward to one of its screens opens it again", () => {
    const { device, frame, loads } = stand();
    appFrame().dispatchEvent(new Event("load"));
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    screen.getByRole("button", { name: "Закрыть" }).click();
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    (appFrame().contentWindow as Window).dispatchEvent(new PopStateEvent("popstate"));
    expect(appFrame()).toBeVisible();
    expect(screen.getByText("Приложение закрыто")).not.toBeVisible();
    expect(loads).toEqual([]);
    expect(device.frame()).toBe(frame);
    screen.getByRole("button", { name: "Сохранить" }).click();
    expect(frame.mainButtonClicked).toHaveBeenCalledOnce();
  });

  it("starts a new document of the app — Back to an earlier start — with Telegram's buttons reset", async () => {
    const { device } = stand();
    device.chrome.backButton(true);
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    device.chrome.closingConfirmation(true);
    device.chrome.ready();
    // The page's own dialog stays, opened while the app loads: «Об этом демо».
    const about = device.dialogs.open({
      kind: "sheet", label: "Об этом демо", choices: [{ text: "Закрыть", value: true }], cancel: false,
    });
    const next = appSide();
    device.chrome.connect(next);
    within(screen.getByRole("dialog", { name: "Об этом демо" })).getByRole("button", { name: "Закрыть" }).click();
    await expect(about).resolves.toBe(true);
    expect(device.frame()).toBe(next);
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    expect(screen.getByText("Приложение загружается")).toBeVisible();
    // No «‹ Назад», and closing asks nothing.
    screen.getByRole("button", { name: "Закрыть" }).click();
    expect(screen.getByText("Приложение закрыто")).toBeVisible();
    // Closed, and then Back starts the app at a screen of an earlier start: it is on the screen again.
    device.chrome.connect(appSide());
    expect(appFrame()).toBeVisible();
    expect(screen.getByText("Приложение закрыто")).not.toBeVisible();
  });

  it("asks whether the bot may write", async () => {
    const { device } = stand();
    const allowed = device.chrome.writeAccess();
    const dialog = screen.getByRole("dialog", { name: "Разрешить боту «Личный помощник» присылать сообщения?" });
    within(dialog).getByRole("button", { name: "Разрешить" }).click();
    await expect(allowed).resolves.toBe(true);
    const refused = device.chrome.writeAccess();
    screen.getByRole("button", { name: "Отмена" }).click();
    await expect(refused).resolves.toBe(false);
  });

  it("shows the README's habit card in the chat picker and sends nothing", async () => {
    vi.useFakeTimers();
    const { device } = stand();
    const sent = device.chrome.share("demo-habit-7-1");
    const sheet = screen.getByRole("dialog", { name: "В Telegram здесь откроется выбор чата" });
    // A screen reader says what the sheet shows as it opens, with focus already on «Отправить».
    expect(sheet).toHaveAccessibleDescription("Пример: карточка привычки");
    const picture = within(sheet).getByRole("img", { name: "Пример: карточка привычки" });
    expect(picture.getAttribute("src")).toMatch(/habit-card\.jpg/);
    expect(within(sheet).getByText("пример")).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Отправить" })).toHaveFocus();
    within(sheet).getByRole("button", { name: "Отправить" }).click();
    await expect(sent).resolves.toBe(true);
    expect(screen.getByText("Это демо — ничего не отправлено")).toBeInTheDocument();
    vi.advanceTimersByTime(2999);
    expect(screen.getByText("Это демо — ничего не отправлено")).toBeInTheDocument();
    vi.advanceTimersByTime(1);
    expect(screen.queryByText("Это демо — ничего не отправлено")).toBeNull();
  });

  it("gives the sheet's first button focus without scrolling the screen to it while it slides in", () => {
    const { device } = stand();
    const focus = vi.spyOn(HTMLElement.prototype, "focus");
    void device.chrome.share("demo-habit-7-1");
    const send = screen.getByRole("button", { name: "Отправить" });
    expect(send).toHaveFocus();
    // The screen hides its overflow, but a script's focus() still scrolls it, to a sheet that starts
    // below it: the header and the app would jump up behind the sheet for its 0.2 s.
    expect(focus.mock.calls[focus.mock.contexts.indexOf(send)]).toEqual([{ preventScroll: true }]);
  });

  it("shows the week's forecast in the visitor's language, and a cancelled picker says nothing", async () => {
    const { device } = stand("en");
    const cancelled = device.chrome.share("demo-forecast-0-1");
    const sheet = screen.getByRole("dialog", { name: "In Telegram, the chat picker opens here" });
    expect(sheet).toHaveAccessibleDescription("Example: the week's forecast");
    const picture = within(sheet).getByRole("img", { name: "Example: the week's forecast" });
    expect(picture.getAttribute("src")).toMatch(/forecast-card\.en\.jpg/);
    within(sheet).getByRole("button", { name: "Cancel" }).click();
    await expect(cancelled).resolves.toBe(false);
    const escaped = device.chrome.share("demo-forecast-0-2");
    press("Escape");
    await expect(escaped).resolves.toBe(false);
    expect(screen.queryByText("This is a demo — nothing was sent")).toBeNull();
  });

  it("draws a phone's status bar and bottom strip, which screen readers skip", () => {
    const { device } = stand();
    device.setTime("10:30");
    const status = document.querySelector(".tg-status") as HTMLElement;
    expect(status).toHaveAttribute("aria-hidden", "true");
    expect(status).toHaveTextContent("10:30");
    expect(status.querySelectorAll("svg")).toHaveLength(3);
    expect(document.querySelector(".tg-bottom .tg-home")).not.toBeNull();
  });

  it("leaves the theme's colours where the app painted its own", () => {
    const { device } = stand();
    device.chrome.paint("header", "#f7f5f2");
    device.chrome.paint("bottom", "#f7f5f2");
    device.unpaint();
    expect((document.querySelector(".tg-top") as HTMLElement).style.backgroundColor).toBe("");
    expect((document.querySelector(".tg-bottom") as HTMLElement).style.backgroundColor).toBe("");
  });

  it("reports the app's screen when the app loads and on each change", () => {
    const onRoute = vi.fn();
    const device = createDevice({ language: () => "ru", words: () => WORDS.ru, onRoute });
    document.body.append(device.element);
    device.open("/weather");
    appFrame().dispatchEvent(new Event("load"));
    expect(onRoute).toHaveBeenLastCalledWith("/weather");
    const app = appFrame().contentWindow as Window;
    app.location.hash = "#/notes";
    app.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(onRoute).toHaveBeenLastCalledWith("/notes");
    expect(device.route()).toBe("/notes");
  });

  it("takes the running app to a screen, and starts a closed one there", () => {
    const { device, loads } = stand();
    const running = appFrame();
    running.dispatchEvent(new Event("load"));
    device.go("/habits");
    expect(appFrame()).toBe(running);
    expect(running.contentWindow?.location.hash).toBe("#/habits");
    screen.getByRole("button", { name: "Закрыть" }).click();
    device.go("/money/new");
    expect(loads).toEqual(["assign ./app.html?start=1#/money/new"]);
    expect(running).toBeVisible();
  });

  it("starts the app afresh in its frame, after the last start or on its screen in its place", () => {
    const { device, loads } = stand();
    device.chrome.backButton(true);
    device.chrome.mainButton({ text: "Сохранить", visible: true, active: true, progress: false });
    device.chrome.ready();
    const running = appFrame();
    running.dispatchEvent(new Event("load"));
    device.open("/weather");
    // The new start's document comes in on its screen; started again there, as another language does.
    (running.contentWindow as Window).location.hash = "#/weather";
    running.dispatchEvent(new Event("load"));
    device.open("/weather");
    // Each start's screens stay in the tab's history: Back to one starts the app there again.
    expect(appFrame()).toBe(running);
    expect(loads).toEqual(["assign ./app.html?start=1#/weather", "replace ./app.html?start=2#/weather"]);
    expect(device.route()).toBe("/weather");
    expect(device.frame()).toBeNull();
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    expect(screen.getByText("Приложение загружается")).toBeVisible();
  });
});
