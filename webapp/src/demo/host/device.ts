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
}

export interface Device {
  element: HTMLElement;
  chrome: Chrome;
  dialogs: Dialogs;
  /** Where the page puts its own parts: the header's right end, and the web view over the app. */
  slots: { end: HTMLElement; view: HTMLElement };
  /** The frame of the app that runs now, as it connected; null while none does. */
  frame(): DemoFrame | null;
  /** Opens the app afresh on a route, in a new frame, as Telegram opens a Mini App. */
  open(route: string): void;
  /** Takes the running app to a route, as a link would; opens the app there when it is closed. */
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

  let iframe: HTMLIFrameElement | null = null;
  let loaded = false;
  let opened = "/";
  let current: DemoFrame | null = null;
  let backShown = false;
  let askBeforeClosing = false;
  let mainState = NO_MAIN_BUTTON;
  let toastTimer: number | undefined;

  const dialogs = createDialogs(
    layer,
    () => [...(options.outside?.() ?? []), top, view, bottom],
    () => focusApp(),
  );

  /** Focus into the app, or onto «Открыть снова» while it is closed. */
  function focusApp(): void {
    if (iframe) iframe.focus();
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
    main.hidden = !state.visible;
    main.setAttribute("aria-disabled", String(!state.active));
    if (state.progress) main.setAttribute("aria-busy", "true");
    else main.removeAttribute("aria-busy");
    spinner.hidden = !state.progress;
    // A button that goes away leaves focus in the app, not on the page.
    if (focused && !state.visible) focusApp();
  }

  /** A line at the bottom of the screen for a while, read out by screen readers. */
  function say(text: string, ms: number): void {
    window.clearTimeout(toastTimer);
    toast.textContent = text;
    toastTimer = window.setTimeout(() => {
      toast.textContent = "";
    }, ms);
  }

  /** As the app's frame leaves: Telegram's buttons go with it. */
  function forget(): void {
    dialogs.dismiss();
    iframe?.remove();
    iframe = null;
    current = null;
    backShown = false;
    askBeforeClosing = false;
    showBack();
    showMain(NO_MAIN_BUTTON);
  }

  function watch(frame: HTMLIFrameElement): void {
    const win = frame.contentWindow;
    if (!win || frame !== iframe) return;
    loaded = true;
    const report = () => options.onRoute?.(routeOf(win.location.hash) ?? opened);
    win.addEventListener("hashchange", report);
    report();
  }

  function open(route: string): void {
    // «Открыть снова» goes away with the panel: focus goes on into the app.
    const reopened = closed.contains(document.activeElement);
    forget();
    opened = route;
    loaded = false;
    closed.hidden = true;
    back.hidden = false;
    loading.hidden = false;
    const frame = h("iframe", { class: "tg-frame", title: words().frame, src: `./app.html#${route}` });
    frame.addEventListener("load", () => watch(frame));
    iframe = frame;
    view.prepend(frame);
    if (reopened) frame.focus();
  }

  function close(): void {
    forget();
    back.hidden = true;
    loading.hidden = true;
    closed.hidden = false;
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
    if (loaded && win) win.location.hash = route;
    else open(route);
  }

  const painted = { header: top, background: view, bottom };

  const chrome: Chrome = {
    connect: (frame) => {
      current = frame;
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
    route: () => (iframe ? (routeOf(iframe.contentWindow?.location.hash ?? "") ?? opened) : opened),
    relocalize,
  };
}
