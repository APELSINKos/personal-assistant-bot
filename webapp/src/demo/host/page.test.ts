import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Note } from "../../api/types";
import { createApi, type ApiOptions, type DemoApi } from "../api";
import type { DemoFrame, HostWindow } from "../bridge/contract";
import { pageAddress, startDemo, type DemoOptions } from "./page";
import { WORDS } from "./words";

// Wednesday 7 October 2026, 10:30 in Moscow.
const MORNING = Date.UTC(2026, 9, 7, 7, 30);

function system(dark = true) {
  const listeners: (() => void)[] = [];
  return {
    matches: dark,
    addEventListener: (_type: "change", listener: () => void) => {
      listeners.push(listener);
    },
    turn(next: boolean) {
      this.matches = next;
      for (const listener of listeners) listener();
    },
  };
}

/** The demo on a test page: `address` as the visitor opened it. */
function open(address = "?lang=ru&theme=dark#/", options: Partial<DemoOptions> = {}) {
  const [search = "", hash = ""] = address.split("#");
  const setAddress = vi.fn<(address: string) => void>();
  const makeApi = vi.fn((settings: ApiOptions): DemoApi => createApi(settings));
  const demo = startDemo(document.body, {
    address: { search, hash: hash ? `#${hash}` : "" },
    setAddress,
    now: () => Date.now(),
    system: system(),
    languages: ["ru-RU"],
    makeApi,
    ...options,
  });
  const frame: DemoFrame = { mainButtonClicked: vi.fn(), backButtonClicked: vi.fn(), themeChanged: vi.fn() };
  demo.host.connect(frame);
  return { demo, frame, setAddress, makeApi };
}

function pitch() {
  return within(document.querySelector(".pitch") as HTMLElement);
}

function appFrame(): HTMLIFrameElement {
  const frame = document.querySelector("iframe");
  if (!frame) throw new Error("No frame of the app");
  return frame;
}

/** The app's frame has loaded: what a browser says with the frame's load event. */
function loaded(): Window {
  appFrame().dispatchEvent(new Event("load"));
  return appFrame().contentWindow as Window;
}

afterEach(() => {
  document.body.replaceChildren();
  document.documentElement.removeAttribute("lang");
  document.documentElement.className = "";
  delete (window as unknown as HostWindow).__demoHost;
});

describe("the page's address", () => {
  it("keeps the app's route and the visitor's language and theme, and the rest as it was", () => {
    expect(pageAddress("", "/", {})).toBe("#/");
    expect(pageAddress("?lang=ru", "/weather", { lang: "en" })).toBe("?lang=en#/weather");
    expect(pageAddress("?at=2026-10-07T10:30&shot=1", "/habits", { theme: "light" })).toBe(
      "?at=2026-10-07T10:30&shot=1&theme=light#/habits",
    );
    expect(pageAddress("?theme=dark&lang=ru", "/", { lang: "en", theme: "light" })).toBe("?theme=light&lang=en#/");
  });
});

describe("the demo's page", () => {
  it("publishes the host for the app's frame and opens the app on the address's screen", () => {
    const { demo } = open("?lang=ru#/weather");
    expect((window as unknown as HostWindow).__demoHost).toBe(demo.host);
    expect(appFrame().getAttribute("src")).toBe("./app.html#/weather");
  });

  it("speaks the language the address names, else the browser's", () => {
    open("?lang=en#/");
    expect(document.documentElement.lang).toBe("en");
    expect(document.title).toBe("Personal Assistant — demo");
    document.body.replaceChildren();
    const kazakh = open("#/", { languages: ["kk-KZ", "en"] });
    expect(kazakh.demo.host.language).toBe("ru");
    document.body.replaceChildren();
    const german = open("?lang=xx#/", { languages: ["de-DE"] });
    expect(german.demo.host.language).toBe("en");
    expect(german.demo.host.user.first_name).toBe("Alex");
  });

  it("tells what it is: the pitch, the ways to try it and the line about the data", () => {
    open();
    expect(screen.getByRole("heading", { level: 1, name: "Личный помощник" })).toBeInTheDocument();
    expect(pitch().getByText("Демо · приложение внутри Telegram")).toBeInTheDocument();
    expect(pitch().getByText(/^Telegram-бот, который не просто скажет «\+12°C»/)).toBeInTheDocument();
    expect(pitch().getByText("Попробовать:")).toBeInTheDocument();
    expect(
      pitch().getByText(
        "Данные выдуманные и живут только в этой вкладке: ничего не сохраняется и никуда не отправляется. "
          + "Время — московское. Telegram и сервер не нужны.",
      ),
    ).toBeInTheDocument();
    expect(pitch().getByRole("link", { name: "Открыть бота в Telegram" })).toHaveAttribute(
      "href", "https://t.me/ikbo63_24_bot",
    );
    expect(pitch().getByRole("link", { name: "Исходный код на GitHub" })).toHaveAttribute("target", "_blank");
  });

  it("drives the phone from the pitch's links", () => {
    const { demo } = open();
    const app = loaded();
    // «Список покупок» opens the data's pinned list «Покупки», the first of its notes.
    for (const [name, route] of [
      ["Отметить привычку", "/habits"], ["Записать трату", "/money/new"], ["Напоминание фразой", "/calendar/new"],
      ["Погода на неделю", "/weather"], ["Список покупок", "/notes/1"],
    ]) {
      const link = pitch().getByRole("link", { name });
      expect(link).toHaveAttribute("href", `#${route}`);
      fireEvent.click(link);
      expect(app.location.hash).toBe(`#${route}`);
      expect(demo.device.route()).toBe(route);
    }
  });

  it("opens the pinned list «Покупки» as the shopping list", () => {
    const notes: Note[] = [
      { id: 4, text: "Собрать в поездку", pinned: true, items: [], created_at: "", updated_at: "" },
      { id: 9, text: "Покупки", pinned: true, items: [], created_at: "", updated_at: "" },
    ];
    const makeApi = (settings: ApiOptions): DemoApi => {
      const api = createApi(settings);
      return (request) => (request.path === "/notes" ? { status: 200, body: notes, headers: {} } : api(request));
    };
    open("?lang=ru#/", { makeApi });
    expect(pitch().getByRole("link", { name: "Список покупок" })).toHaveAttribute("href", "#/notes/9");
  });

  it("opens a closed app again from a link of the pitch", () => {
    open();
    screen.getAllByRole("button", { name: "Закрыть" })[0]?.click();
    expect(document.querySelector("iframe")).toBeNull();
    fireEvent.click(pitch().getByRole("link", { name: "Погода на неделю" }));
    expect(appFrame().getAttribute("src")).toBe("./app.html#/weather");
  });

  it("keeps the app's route in the address", () => {
    const { setAddress } = open("?lang=ru&theme=dark#/");
    const app = loaded();
    app.location.hash = "#/notes";
    app.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(setAddress).toHaveBeenLastCalledWith("?lang=ru&theme=dark#/notes");
  });

  it("switches the language: new data in it, and a new frame on the same screen", () => {
    const { demo, setAddress, makeApi } = open("?theme=dark#/weather");
    expect(makeApi).toHaveBeenLastCalledWith(expect.objectContaining({ language: "ru" }));
    const before = appFrame();
    fireEvent.click(within(pitch().getByRole("group", { name: "Язык:" })).getByRole("button", { name: "EN" }));
    expect(demo.host.language).toBe("en");
    expect(demo.host.user).toEqual({ id: 1, first_name: "Alex", language_code: "en" });
    expect(makeApi).toHaveBeenLastCalledWith(expect.objectContaining({ language: "en" }));
    expect(demo.host.api({ method: "GET", path: "/me", search: "", body: null }).body).toMatchObject({
      first_name: "Alex",
    });
    expect(appFrame()).not.toBe(before);
    expect(appFrame().getAttribute("src")).toBe("./app.html#/weather");
    expect(appFrame()).toHaveAttribute("title", "The Personal Assistant app");
    expect(document.documentElement.lang).toBe("en");
    expect(document.title).toBe("Personal Assistant — demo");
    expect(setAddress).toHaveBeenLastCalledWith("?theme=dark&lang=en#/weather");
    for (const button of screen.getAllByRole("button", { name: "EN" })) {
      expect(button).toHaveAttribute("aria-pressed", "true");
    }
    expect(screen.getByRole("heading", { level: 1, name: "Personal Assistant" })).toBeInTheDocument();
  });

  it("switches the theme in place: no new frame, the app hears of it", () => {
    const { demo, frame, setAddress } = open("?lang=ru#/");
    const before = appFrame();
    demo.host.paint("header", "#0a0913");
    fireEvent.click(within(pitch().getByRole("group", { name: "Тема:" })).getByRole("button", { name: "светлая" }));
    expect(demo.host.scheme()).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(frame.themeChanged).toHaveBeenCalledOnce();
    expect(appFrame()).toBe(before);
    expect((document.querySelector(".tg-top") as HTMLElement).style.backgroundColor).toBe("");
    expect(setAddress).toHaveBeenLastCalledWith("?lang=ru&theme=light#/");
  });

  it("follows the system's theme until the visitor picks one", () => {
    const dark = system(true);
    const { demo, frame } = open("?lang=ru#/", { system: dark });
    expect(demo.host.scheme()).toBe("dark");
    dark.turn(false);
    expect(demo.host.scheme()).toBe("light");
    expect(frame.themeChanged).toHaveBeenCalledOnce();
    fireEvent.click(within(pitch().getByRole("group", { name: "Тема:" })).getByRole("button", { name: "тёмная" }));
    dark.turn(false);
    expect(demo.host.scheme()).toBe("dark");
  });

  it("keeps the theme the address names, whatever the system's", () => {
    const light = system(false);
    const { demo } = open("?theme=dark#/", { system: light });
    expect(demo.host.scheme()).toBe("dark");
    light.turn(true);
    light.turn(false);
    expect(demo.host.scheme()).toBe("dark");
  });

  it("starts over: new data and «Сегодня»", () => {
    const { makeApi, setAddress } = open("?lang=ru#/weather");
    const before = appFrame();
    makeApi.mockClear();
    fireEvent.click(pitch().getByRole("button", { name: "Начать заново" }));
    expect(makeApi).toHaveBeenCalledOnce();
    expect(makeApi).toHaveBeenCalledWith(expect.objectContaining({ language: "ru" }));
    expect(appFrame()).not.toBe(before);
    expect(appFrame().getAttribute("src")).toBe("./app.html#/");
    expect(setAddress).toHaveBeenLastCalledWith("?lang=ru#/");
  });

  it("writes nothing into the browser", () => {
    open();
    fireEvent.click(within(pitch().getByRole("group", { name: "Язык:" })).getByRole("button", { name: "EN" }));
    fireEvent.click(within(pitch().getByRole("group", { name: "Theme:" })).getByRole("button", { name: "light" }));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });
});

describe("the demo's menu", () => {
  function menuButton() {
    return screen.getByRole("button", { name: "Меню демо" });
  }

  it("opens with «⋯» and holds the switches, «Начать заново», «Об этом демо» and the links", () => {
    open();
    const button = menuButton();
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const menu = within(document.getElementById(button.getAttribute("aria-controls") ?? "") as HTMLElement);
    expect(menu.getByRole("group", { name: "Язык:" })).toBeInTheDocument();
    expect(menu.getByRole("group", { name: "Тема:" })).toBeInTheDocument();
    expect(menu.getByRole("button", { name: "Начать заново" })).toBeInTheDocument();
    expect(menu.getByRole("button", { name: "Об этом демо" })).toBeInTheDocument();
    expect(menu.getByRole("link", { name: "Открыть бота в Telegram" })).toBeInTheDocument();
    expect(menu.getByRole("link", { name: "Исходный код на GitHub" })).toBeInTheDocument();
    expect(menu.getByRole("button", { name: "RU" })).toHaveFocus();
  });

  it("closes with Esc and gives focus back to «⋯»", () => {
    open();
    fireEvent.click(menuButton());
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(menuButton()).toHaveFocus();
    expect(document.getElementById(menuButton().getAttribute("aria-controls") ?? "")).not.toBeVisible();
  });

  it("closes when the visitor taps elsewhere", () => {
    open();
    fireEvent.click(menuButton());
    fireEvent.pointerDown(document.querySelector(".pitch") as HTMLElement);
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when focus leaves it, backwards past «⋯» as well as forwards", () => {
    open();
    fireEvent.click(menuButton());
    // Shift+Tab from the first item: «⋯» keeps the menu open, the header's «Закрыть» before it does not.
    menuButton().focus();
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");
    screen.getByRole("button", { name: "Закрыть" }).focus();
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById(menuButton().getAttribute("aria-controls") ?? "")).not.toBeVisible();
    // Tab from the last item goes into the app's frame, and a browser says so with the page's blur.
    fireEvent.click(menuButton());
    const menu = within(document.getElementById(menuButton().getAttribute("aria-controls") ?? "") as HTMLElement);
    menu.getByRole("link", { name: "Исходный код на GitHub" }).focus();
    appFrame().focus();
    fireEvent.blur(window);
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("switches the language from the menu and closes", () => {
    const { demo } = open();
    fireEvent.click(menuButton());
    const menu = within(document.getElementById(menuButton().getAttribute("aria-controls") ?? "") as HTMLElement);
    fireEvent.click(menu.getByRole("button", { name: "EN" }));
    expect(demo.host.language).toBe("en");
    expect(screen.getByRole("button", { name: "Demo menu" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Demo menu" })).toHaveFocus();
  });

  it("tells about the demo in a dialog, and gives focus back to «⋯»", () => {
    open();
    fireEvent.click(menuButton());
    fireEvent.click(screen.getByRole("button", { name: "Об этом демо" }));
    const dialog = screen.getByRole("dialog", { name: "Об этом демо" });
    // Focus starts on «Закрыть», at the end: a screen reader says the sheet's text as it opens.
    expect(dialog).toHaveAccessibleDescription([WORDS.ru.tagline, WORDS.ru.data, WORDS.ru.aboutText].join(" "));
    const about = within(dialog);
    expect(about.getByText(/^Telegram-бот, который не просто скажет/)).toBeInTheDocument();
    expect(about.getByText(/^Данные выдуманные и живут только в этой вкладке/)).toBeInTheDocument();
    expect(
      about.getByText(
        "Это то же приложение, что открывается в Telegram, без единой правки: вместо сервера ему отвечают "
          + "выдуманные данные прямо в этой странице.",
      ),
    ).toBeInTheDocument();
    about.getByRole("button", { name: "Закрыть" }).click();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(menuButton()).toHaveFocus();
  });
});

describe("the demo's phone", () => {
  it("says for 4 s on every load that it is a demo", () => {
    vi.useFakeTimers();
    open();
    const hint = document.querySelector(".demo-hint") as HTMLElement;
    expect(hint).toHaveAttribute("role", "status");
    vi.advanceTimersByTime(0);
    expect(hint).toHaveTextContent(
      "Это демо: данные выдуманные, ничего не сохраняется, время московское",
    );
    vi.advanceTimersByTime(3999);
    expect(hint).toHaveTextContent("Это демо");
    vi.advanceTimersByTime(1);
    expect(hint).toBeEmptyDOMElement();
  });

  it("shows Moscow time in the status bar, hidden from screen readers", () => {
    vi.useFakeTimers();
    vi.setSystemTime(MORNING);
    open();
    const time = document.querySelector(".tg-status__time") as HTMLElement;
    expect(time).toHaveTextContent("10:30");
    expect(time.closest("[aria-hidden='true']")).not.toBeNull();
    vi.advanceTimersByTime(60_000);
    expect(time).toHaveTextContent("10:31");
  });

  it("runs the status bar's clock from the moment ?at= names", () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.UTC(2026, 0, 15, 20, 5));
    open("?lang=ru&at=2026-10-07T10:30#/");
    expect(document.querySelector(".tg-status__time")).toHaveTextContent("10:30");
  });

  it("shows only the device in shot mode, with no hint", () => {
    vi.useFakeTimers();
    open("?shot=1&at=2026-10-07T10:30&lang=en&theme=light#/weather");
    expect(document.querySelector(".demo")).toHaveClass("demo--shot");
    vi.advanceTimersByTime(0);
    expect(document.querySelector(".demo-hint")).toBeEmptyDOMElement();
  });
});
