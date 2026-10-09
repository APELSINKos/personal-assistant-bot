/**
 * The demo's page (spec §6): on a wide screen the pitch beside the device in a phone's frame, on a
 * phone the device alone, with the switches in the header's «⋯» menu; the language, the theme and
 * the app's screen kept in the address; and with ?shot=1 nothing but the device's screen, for the
 * README's pictures. It also keeps what Telegram keeps outside the app — the language, the visitor,
 * the clock, the theme and the API — as the host the app's frame finds: `window.parent.__demoHost`.
 * Nothing is written into the browser: a reload starts the demo afresh.
 */
import type { Note } from "../../api/types";
import { resolveLang, type Lang } from "../../i18n";
import { createApi, type ApiOptions, type DemoApi } from "../api";
import { moscowTime, parseAt } from "../api/clock";
import { WORDS as DATA } from "../api/words";
import type { DemoHost, HostWindow } from "../bridge/contract";
import { createDevice, routeOf, type Device } from "./device";
import { h, icon } from "./dom";
import { LINKS, WORDS, type HostWords } from "./words";

export type Scheme = "dark" | "light";

/** What the visitor picked on the page: it goes into the address. */
interface Chosen {
  lang?: Lang;
  theme?: Scheme;
}

export interface DemoOptions {
  /** The page's address as it was opened. */
  address: { search: string; hash: string };
  /** Puts an address relative to the page into the address bar, without a step in the history. */
  setAddress: (address: string) => void;
  /** The real clock. */
  now: () => number;
  /** Whether the system's theme is dark, followed until the visitor picks one. */
  system: { matches: boolean; addEventListener(type: "change", listener: () => void): void };
  /** The browser's languages; the first one counts. */
  languages: readonly string[];
  /** Makes the demo's API with its data: on every start, and anew in another language. */
  makeApi?: (options: ApiOptions) => DemoApi;
}

export interface Demo {
  host: DemoHost;
  device: Device;
}

/** How long a phone shows that this is a demo. */
const HINT_FOR = 4000;

/** Where the pitch's links take the phone; the shopping list is a note, found by its title. */
const TRIES: { name: keyof HostWords["tries"]; route: string }[] = [
  { name: "habit", route: "/habits" },
  { name: "expense", route: "/money/new" },
  { name: "phrase", route: "/calendar/new" },
  { name: "weather", route: "/weather" },
  { name: "shopping", route: "/notes" },
];

/**
 * The page's address for the app's route: the query as it was opened, with the language and the
 * theme the visitor picked, and the route as the hash.
 */
export function pageAddress(search: string, route: string, chosen: Chosen): string {
  const parts = search.replace(/^\?/, "").split("&").filter((part) => part !== "");
  const put = (name: string, value: string | undefined) => {
    if (value === undefined) return;
    const index = parts.findIndex((part) => part.split("=")[0] === name);
    if (index === -1) parts.push(`${name}=${value}`);
    else parts[index] = `${name}=${value}`;
  };
  put("lang", chosen.lang);
  put("theme", chosen.theme);
  return `${parts.length > 0 ? `?${parts.join("&")}` : ""}#${route}`;
}

/** A plain click: one with a modifier or another button opens the link as a link. */
function plain(event: MouseEvent): boolean {
  return event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;
}

export function startDemo(root: HTMLElement, options: DemoOptions): Demo {
  const query = new URLSearchParams(options.address.search);
  const asked = query.get("lang");
  let language: Lang = asked === "ru" || asked === "en" ? asked : resolveLang(options.languages[0]);
  const at = parseAt(query.get("at"));
  const clockOffset = at === null ? null : at - options.now();
  const clock = () => options.now() + (clockOffset ?? 0);
  const shot = query.get("shot") === "1";
  const makeApi = options.makeApi ?? createApi;
  let api = makeApi({ language, now: clock });
  const chosen: Chosen = {};

  // ?theme= or the system's; until the visitor picks one, the theme follows the system.
  const themed = query.get("theme");
  let scheme: Scheme = themed === "dark" || themed === "light" ? themed : options.system.matches ? "dark" : "light";
  let followSystem = themed !== "dark" && themed !== "light";

  const words = () => WORDS[language];
  // Every text of the page, said again when the language changes.
  const speakers: ((w: HostWords) => void)[] = [];
  const say = <E extends Element>(element: E, pick: (w: HostWords) => string): E => {
    speakers.push((w) => {
      element.textContent = pick(w);
    });
    return element;
  };
  const name = <E extends Element>(element: E, pick: (w: HostWords) => string): E => {
    speakers.push((w) => element.setAttribute("aria-label", pick(w)));
    return element;
  };

  const writeAddress = (route: string) => options.setAddress(pageAddress(options.address.search, route, chosen));
  const pitch = h("section", { class: "pitch", "aria-labelledby": "pitch-title" });
  const device = createDevice({ language: () => language, words, outside: () => [pitch], onRoute: writeAddress });

  // The switches, on the page and in the menu alike.
  const pressed: { button: HTMLButtonElement; on: () => boolean }[] = [];
  function option(text: string | ((w: HostWords) => string), on: () => boolean, act: () => void) {
    const button = h("button", { type: "button", class: "switch__option" });
    if (typeof text === "string") button.textContent = text;
    else say(button, text);
    button.addEventListener("click", act);
    pressed.push({ button, on });
    return button;
  }
  function switches(place: string): HTMLElement {
    const group = (label: (w: HostWords) => string, id: string, ...buttons: HTMLButtonElement[]) =>
      h(
        "div",
        { class: "switch", role: "group", "aria-labelledby": id },
        say(h("span", { class: "switch__label", id }), label),
        ...buttons,
      );
    return h(
      "div",
      { class: "switches" },
      group(
        (w) => w.language,
        `${place}-language`,
        option("RU", () => language === "ru", () => setLanguage("ru")),
        option("EN", () => language === "en", () => setLanguage("en")),
      ),
      group(
        (w) => w.theme,
        `${place}-theme`,
        option((w) => w.dark, () => scheme === "dark", () => setTheme("dark")),
        option((w) => w.light, () => scheme === "light", () => setTheme("light")),
      ),
    );
  }
  const showPressed = () => {
    for (const { button, on } of pressed) button.setAttribute("aria-pressed", String(on()));
  };
  const link = (href: string, pick: (w: HostWords) => string, className: string) =>
    say(h("a", { class: className, href, target: "_blank", rel: "noopener" }), pick);

  // The pitch: what this is, where to look, the switches and the links.
  const tries = TRIES.map(({ name: key, route }) => {
    const anchor = say(h("a", { class: "pitch__try", href: `#${route}` }), (w) => w.tries[key]);
    const target = key === "shopping" ? shoppingList : () => route;
    anchor.addEventListener("click", (event) => {
      if (!plain(event)) return;
      event.preventDefault();
      device.go(target());
    });
    return { anchor, target };
  });
  const showTries = () => {
    for (const { anchor, target } of tries) anchor.setAttribute("href", `#${target()}`);
  };
  const pitchStartOver = say(h("button", { type: "button", class: "host-button" }), (w) => w.startOver);
  pitchStartOver.addEventListener("click", startOver);
  pitch.append(
    say(h("p", { class: "pitch__kicker" }), (w) => w.kicker),
    say(h("h1", { class: "pitch__title", id: "pitch-title" }), (w) => w.name),
    say(h("p", { class: "pitch__tagline" }), (w) => w.tagline),
    say(h("p", { class: "pitch__label", id: "pitch-tries" }), (w) => w.tryIt),
    h(
      "ul",
      { class: "pitch__tries", "aria-labelledby": "pitch-tries" },
      ...tries.map(({ anchor }) => h("li", {}, anchor)),
    ),
    switches("pitch"),
    h(
      "div",
      { class: "pitch__actions" },
      pitchStartOver,
      link(LINKS.bot, (w) => w.bot, "host-button host-button--primary"),
      link(LINKS.source, (w) => w.source, "host-button"),
    ),
    say(h("p", { class: "pitch__data" }), (w) => w.data),
  );

  // The «⋯» menu, where Telegram keeps its own: the same switches and links, and «Об этом демо».
  const menuButton = name(
    h("button", { type: "button", class: "tg-header__menu", "aria-expanded": "false", "aria-controls": "demo-menu" }),
    (w) => w.menu,
  );
  menuButton.append(icon("more"));
  const menuStartOver = say(h("button", { type: "button", class: "tg-menu__item" }), (w) => w.startOver);
  const menuAbout = say(h("button", { type: "button", class: "tg-menu__item" }), (w) => w.about);
  const menu = h(
    "div",
    { class: "tg-menu", id: "demo-menu", hidden: true },
    switches("menu"),
    menuStartOver,
    menuAbout,
    link(LINKS.bot, (w) => w.bot, "tg-menu__item"),
    link(LINKS.source, (w) => w.source, "tg-menu__item"),
  );
  device.slots.end.append(menuButton, menu);

  function openMenu(): void {
    menu.hidden = false;
    menuButton.setAttribute("aria-expanded", "true");
    menu.querySelector<HTMLElement>("button, a")?.focus();
  }
  function closeMenu(focusButton: boolean): void {
    if (menu.hidden) return;
    menu.hidden = true;
    menuButton.setAttribute("aria-expanded", "false");
    if (focusButton) menuButton.focus();
  }
  menuButton.addEventListener("click", () => (menu.hidden ? openMenu() : closeMenu(true)));
  // An item does its work with the menu closed and focus back on «⋯».
  menu.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("button, a")) closeMenu(true);
  }, true);
  menuStartOver.addEventListener("click", startOver);
  menuAbout.addEventListener("click", about);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      event.preventDefault();
      closeMenu(true);
    }
  });
  document.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Node ? event.target : null;
    if (!menu.contains(target) && !menuButton.contains(target)) closeMenu(false);
  });
  // Focus that leaves the menu, into the app's frame too, closes it.
  menu.addEventListener("focusout", (event) => {
    const next = event.relatedTarget instanceof Node ? event.relatedTarget : null;
    if (next && !menu.contains(next) && next !== menuButton) closeMenu(false);
  });
  window.addEventListener("blur", () => closeMenu(false));

  function about(): void {
    const w = words();
    void device.dialogs
      .open({
        kind: "sheet",
        label: w.about,
        content: [
          h("p", { class: "dialog__text" }, w.tagline),
          h("p", { class: "dialog__text" }, w.data),
          h("p", { class: "dialog__text" }, w.aboutText),
        ],
        choices: [{ text: w.close, value: true, primary: true }],
        cancel: false,
      })
      .catch(() => false);
  }

  // A phone says on every load, for a while, that this is a demo: it has no status bar with the
  // demo's clock.
  const hint = h("p", { class: "demo-hint", role: "status" });
  speakers.push((w) => {
    if (hint.textContent) hint.textContent = w.hint;
  });
  device.slots.view.append(hint);
  if (!shot) {
    window.setTimeout(() => {
      hint.textContent = words().hint;
      window.setTimeout(() => {
        hint.textContent = "";
      }, HINT_FOR);
    }, 0);
  }

  // The status bar's clock: Moscow time, on the minute.
  const tick = () => {
    const now = clock();
    device.setTime(moscowTime(now));
    window.setTimeout(tick, 60_000 - (now % 60_000));
  };
  tick();

  /** The pinned list «Покупки» of the data, or the notes when there is none. */
  function shoppingList(): string {
    const reply = api({ method: "GET", path: "/notes", search: "", body: null });
    const notes = reply.status === 200 && Array.isArray(reply.body) ? (reply.body as Note[]) : [];
    const list = notes.find((note) => note.pinned && note.text === DATA[language].shopping);
    return list ? `/notes/${list.id}` : "/notes";
  }

  function speak(): void {
    const w = words();
    document.documentElement.lang = language;
    document.title = w.title;
    for (const speaker of speakers) speaker(w);
    device.relocalize();
    showPressed();
    showTries();
  }

  function setLanguage(next: Lang): void {
    if (next === language) return;
    language = next;
    chosen.lang = next;
    // New data in the new language, and the app afresh on the same screen: no screen mixes the two.
    api = makeApi({ language, now: clock });
    speak();
    const route = device.route();
    device.open(route);
    writeAddress(route);
  }

  function showTheme(next: Scheme): void {
    if (next === scheme) return;
    scheme = next;
    document.documentElement.dataset.theme = next;
    device.unpaint();
    device.frame()?.themeChanged();
    showPressed();
  }

  function setTheme(next: Scheme): void {
    followSystem = false;
    chosen.theme = next;
    showTheme(next);
    writeAddress(device.route());
  }

  options.system.addEventListener("change", () => {
    if (followSystem) showTheme(options.system.matches ? "dark" : "light");
  });

  function startOver(): void {
    api = makeApi({ language, now: clock });
    showTries();
    device.open("/");
    writeAddress("/");
  }

  const host: DemoHost = {
    get language() {
      return language;
    },
    get user() {
      return { id: 1, first_name: DATA[language].name, language_code: language };
    },
    clockOffset,
    scheme: () => scheme,
    api: (request) => api(request),
    ...device.chrome,
  };

  document.documentElement.dataset.theme = scheme;
  root.append(h("div", { class: shot ? "demo demo--shot" : "demo" }, pitch, device.element));
  speak();
  // The host is in place before the app's frame starts: the frame looks for it at once.
  (window as unknown as HostWindow).__demoHost = host;
  device.open(routeOf(options.address.hash) ?? "/");
  return { host, device };
}
