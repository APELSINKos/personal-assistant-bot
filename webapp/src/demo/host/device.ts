/**
 * The demo's device (spec §4.3, §6): what Telegram draws around a Mini App, drawn by the host page
 * around the app's frame — the header with «✕ Закрыть» or «‹ Назад» and the bot's name, the web
 * view with the app, the main button's bar under it, the dialogs and the chat picker inside the
 * screen, and the panel left when the app is closed — and what a phone draws around that: the status
 * bar and the strip at the bottom, shown only in a phone's frame and in shot mode. Nothing goes into
 * the app's document: the host only answers what the frame's bridge asks, without Telegram's logo
 * or name.
 */
import type { Lang } from "../../i18n";
import type { DemoFrame, DemoHost, MainButtonState } from "../bridge/contract";
import { createDialogs, type Dialogs } from "./dialogs";
import { h, icon } from "./dom";
import { sample } from "./share";
import { LINKS, type HostWords } from "./words";

/** Telegram's chrome, as the frame's bridge reaches it. */
export type Chrome = Pick<
  DemoHost,
  "connect" | "ready" | "paint" | "backButton" | "mainButton" | "closingConfirmation" | "confirm" | "writeAccess"
  | "share"
>;

export interface DeviceOptions {
  /** The visitor's language now: the chat picker's sample is in it. */
  language: () => Lang;
  words: () => HostWords;
  /** The rest of the page, inert while a dialog is open. */
  outside?: () => Element[];
  /** The app went to another screen, «/weather». */
  onRoute?: (route: string) => void;
  /**
   * Loads an address into the app's frame: as a step of the tab's history after the document it
   * holds, or with `replace` in its place — Location.assign and Location.replace. Tests stand in for
   * it, as jsdom loads no frame.
   */
  load?: (frame: Window, address: string, replace: boolean) => void;
}

export interface Device {
  element: HTMLElement;
  chrome: Chrome;
  dialogs: Dialogs;
  /** Where the page puts its own parts: the header's right end, and the web view over the app. */
  slots: { end: HTMLElement; view: HTMLElement };
  /** The frame of the app that runs now, as it connected; null while none does. */
  frame(): DemoFrame | null;
  /** Starts the app afresh on a route, as Telegram opens a Mini App: a new document in its frame. */
  open(route: string): void;
  /** Takes the running app to a route, as a link would; starts the app there when it is closed. */
  go(route: string): void;
  /** Leaves the theme's own colours where the app painted its: a new theme, until it paints again. */
  unpaint(): void;
  /** The status bar's clock, «10:30». */
  setTime(time: string): void;
  /** The route the app shows now, «/weather». */
  route(): string;
  /** Says everything again in the visitor's language now. */
  relocalize(): void;
}

/** How long the line after «Отправить» stays. */
const SENT_FOR = 3000;

const NO_MAIN_BUTTON: MainButtonState = { text: "", visible: false, active: true, progress: false };

/** The app's route in a hash, «#/weather» → «/weather»; null for any other hash. */
export function routeOf(hash: string): string | null {
  return hash.startsWith("#/") ? hash.slice(1) : null;
}

export function createDevice(options: DeviceOptions): Device {
  const { words } = options;

  const back = h("button", { type: "button", class: "tg-header__back" });
  const name = h("span", { class: "tg-header__name" });
  const demo = h("span", { class: "tg-header__demo" });
  const end = h("span", { class: "tg-header__end" });
  const header = h(
    "header",
    { class: "tg-header" },
    back,
    h("p", { class: "tg-header__title" }, name, demo),
    end,
  );
  // The phone's own status bar: a picture of one, which screen readers skip.
  const time = h("span", { class: "tg-status__time" });
  const status = h(
    "div",
    { class: "tg-status", "aria-hidden": "true" },
    time,
    h("span", { class: "tg-status__icons" }, icon("signal"), icon("wifi"), icon("battery")),
  );
  const top = h("div", { class: "tg-top" }, status, header);

  const loadingText = h("span", { class: "visually-hidden" });
  const loading = h(
    "div",
    { class: "tg-loading", role: "status" },
    h("span", { class: "tg-loading__block" }),
    h("span", { class: "tg-loading__block" }),
    h("span", { class: "tg-loading__block" }),
    loadingText,
  );
  const closedTitle = h("p", { class: "tg-closed__title" });
  const reopen = h("button", { type: "button", class: "host-button host-button--primary" });
  const botLink = h("a", { class: "host-button", href: LINKS.bot, target: "_blank", rel: "noopener" });
  const sourceLink = h("a", { class: "host-button", href: LINKS.source, target: "_blank", rel: "noopener" });
  const closed = h("div", { class: "tg-closed", hidden: true }, closedTitle, reopen, botLink, sourceLink);
  const toast = h("p", { class: "tg-toast", role: "status" });
  const view = h("div", { class: "tg-view" }, loading, closed, toast);

  const mainText = h("span", { class: "tg-main__text" });
  const spinner = h("span", { class: "tg-main__spinner", "aria-hidden": "true", hidden: true });
  const main = h("button", { type: "button", class: "tg-main", hidden: true }, mainText, spinner);
  const bottom = h("div", { class: "tg-bottom" }, main, h("div", { class: "tg-home" }));

  const layer = h("div", { class: "tg-layer" });
  const screen = h("div", { class: "device__screen" }, top, view, bottom, layer);
  const element = h("div", { class: "device" }, screen);

  // One frame for the visit, each start of the app a new document in it: the screens of every start
  // stay in the tab's history, and Back to one of an earlier start loads the app there again, with
  // the visit's data.
  let iframe: HTMLIFrameElement | null = null;
  /** The app is on the screen; false while the panel «Приложение закрыто» is. */
  let shown = false;
  let loaded = false;
  let opened = "/";
  /** The starts after the first, each at an address of its own: the frame loads it even on the route it shows. */
  let starts = 0;
  let current: DemoFrame | null = null;
  let backShown = false;
  let askBeforeClosing = false;
  let mainState = NO_MAIN_BUTTON;
  let toastTimer: number | undefined;
  const load = options.load ?? ((frame: Window, address: string, replace: boolean) => {
    if (replace) frame.location.replace(address);
    else frame.location.assign(address);
  });

  const dialogs = createDialogs(
    layer,
    () => [...(options.outside?.() ?? []), top, view, bottom],
    () => focusApp(),
  );

  /** Focus into the app, or onto «Открыть снова» while it is closed. */
  function focusApp(): void {
    if (iframe && shown) iframe.focus();
    else reopen.focus();
  }

  function showBack(): void {
    const w = words();
    back.replaceChildren(icon(backShown ? "back" : "close"), h("span", {}, backShown ? w.back : w.close));
  }

  function showMain(state: MainButtonState): void {
    const focused = document.activeElement === main;
    mainState = state;
    mainText.textContent = state.text;
    // Only with the app on the screen: a closed app keeps its button for when it is back.
    main.hidden = !state.visible || !shown;
    main.setAttribute("aria-disabled", String(!state.active));
    if (state.progress) main.setAttribute("aria-busy", "true");
    else main.removeAttribute("aria-busy");
    spinner.hidden = !state.progress;
    // A button that goes away leaves focus in the app, not on the page.
    if (focused && main.hidden) focusApp();
  }

  /** A line at the bottom of the screen for a while, read out by screen readers. */
  function say(text: string, ms: number): void {
    window.clearTimeout(toastTimer);
    toast.textContent = text;
    toastTimer = window.setTimeout(() => {
      toast.textContent = "";
    }, ms);
  }

  /** Telegram's buttons as the app finds them on a new start: none of the last start's. */
  function reset(): void {
    current = null;
    backShown = false;
    askBeforeClosing = false;
    showBack();
    showMain(NO_MAIN_BUTTON);
  }

  /** The app on the screen in place of the panel: focus on «Открыть снова» goes on into the app. */
  function show(): void {
    if (shown) return;
    const reopened = closed.contains(document.activeElement);
    shown = true;
    closed.hidden = true;
    back.hidden = false;
    if (iframe) iframe.hidden = false;
    showMain(mainState);
    if (reopened) iframe?.focus();
  }

  function watch(frame: HTMLIFrameElement): void {
    const win = frame.contentWindow;
    if (!win) return;
    loaded = true;
    const report = () => options.onRoute?.(routeOf(win.location.hash) ?? opened);
    win.addEventListener("hashchange", report);
    // Back or Forward to one of the app's screens while it is closed opens it again there.
    win.addEventListener("popstate", show);
    report();
  }

  /** The route the app shows now, «/weather»; until its document is in, the one it was started on. */
  function shownRoute(): string {
    const hash = iframe && loaded ? iframe.contentWindow?.location.hash : undefined;
    return routeOf(hash ?? "") ?? opened;
  }

  function open(route: string): void {
    const same = route === shownRoute();
    // The last start goes, and its dialog with it.
    dialogs.dismiss();
    reset();
    opened = route;
    loaded = false;
    loading.hidden = false;
    if (iframe) {
      // In place of the last start on the screen it shows (another language), else after it: Back
      // then goes from the new start to where the last one was.
      starts += 1;
      const win = iframe.contentWindow;
      if (win) load(win, `./app.html?start=${starts}#${route}`, same);
    } else {
      const frame = h("iframe", { class: "tg-frame", title: words().frame, src: `./app.html#${route}` });
      frame.addEventListener("load", () => watch(frame));
      iframe = frame;
      view.prepend(frame);
    }
    show();
  }

  function close(): void {
    // Out of sight, as Telegram closes it, but kept as it was: Back or Forward to one of its screens
    // opens it again there, and «Открыть снова» starts it afresh.
    shown = false;
    if (iframe) iframe.hidden = true;
    back.hidden = true;
    loading.hidden = true;
    closed.hidden = false;
    showMain(mainState);
    reopen.focus();
  }

  async function askToClose(): Promise<void> {
    if (askBeforeClosing) {
      const w = words();
      const sure = await dialogs
        .open({
          kind: "question",
          label: w.closing,
          choices: [{ text: w.cancel, value: false }, { text: w.closeAnyway, value: true, primary: true }],
          cancel: false,
        })
        .catch(() => false);
      if (!sure) return;
    }
    close();
  }

  back.addEventListener("click", () => {
    if (backShown) current?.backButtonClicked();
    else void askToClose();
  });
  main.addEventListener("click", () => {
    if (mainState.active) current?.mainButtonClicked();
  });
  reopen.addEventListener("click", () => open("/"));

  function go(route: string): void {
    const win = iframe?.contentWindow;
    if (shown && loaded && win) win.location.hash = route;
    else open(route);
  }

  const painted = { header: top, background: view, bottom };

  const chrome: Chrome = {
    connect: (frame) => {
      // A new document of the app — a new start, or Back to a screen of an earlier one — finds
      // Telegram's buttons as a Mini App finds them on its start, and is on the screen. A dialog
      // stays: the page's own may be open while the app loads.
      reset();
      current = frame;
      loading.hidden = false;
      show();
    },
    ready: () => {
      loading.hidden = true;
    },
    paint: (part, color) => {
      painted[part].style.backgroundColor = color;
    },
    backButton: (visible) => {
      backShown = visible;
      showBack();
    },
    mainButton: (state) => showMain({ ...state }),
    closingConfirmation: (enabled) => {
      askBeforeClosing = enabled;
    },
    confirm: (message) => {
      const w = words();
      return dialogs.open({
        kind: "question",
        label: message,
        choices: [{ text: w.cancel, value: false }, { text: w.ok, value: true, primary: true }],
        cancel: false,
      });
    },
    writeAccess: () => {
      const w = words();
      return dialogs.open({
        kind: "question",
        label: w.writeAccess,
        choices: [{ text: w.cancel, value: false }, { text: w.allow, value: true, primary: true }],
        cancel: false,
      });
    },
    share: async (preparedId) => {
      const w = words();
      const sent = await dialogs.open({
        kind: "sheet",
        label: w.shareTitle,
        content: [sample(preparedId, options.language(), w)],
        choices: [{ text: w.send, value: true, primary: true }, { text: w.cancel, value: false }],
        cancel: false,
      });
      if (sent) say(w.sent, SENT_FOR);
      return sent;
    },
  };

  function relocalize(): void {
    const w = words();
    name.textContent = w.name;
    demo.textContent = w.demo;
    loadingText.textContent = w.loading;
    closedTitle.textContent = w.closed;
    reopen.textContent = w.openAgain;
    botLink.textContent = w.bot;
    sourceLink.textContent = w.source;
    if (iframe) iframe.title = w.frame;
    showBack();
  }

  relocalize();
  return {
    element,
    chrome,
    dialogs,
    slots: { end, view },
    frame: () => current,
    open,
    go,
    unpaint: () => {
      for (const part of Object.values(painted)) part.style.backgroundColor = "";
    },
    setTime: (text) => {
      time.textContent = text;
    },
    route: shownRoute,
    relocalize,
  };
}
