/**
 * Telegram's WebApp object for the app in the demo's frame (spec §4.3). What Telegram draws around
 * the app — the back button, the main button, dialogs, the chat picker — the host page draws: each
 * call goes to the host as plain data, and what the visitor does there comes back as Telegram's
 * events. The app's own module stays as it is and finds this object where telegram-web-app.js puts
 * Telegram's.
 */
import type { TgWebApp } from "../../telegram";
import type { DemoHost, MainButtonState } from "./contract";

/** The Bot API version the demo speaks: every branch of the app from 6.1 to 8.0 runs. */
const VERSION = "8.0";

type Listener = (data?: unknown) => void;

/** As telegram-web-app.js compares them: part by part, as numbers, so 7.10 is above 7.9. */
function compareVersions(a: string, b: string): number {
  const left = a.split(".").map((part) => Number.parseInt(part, 10) || 0);
  const right = b.split(".").map((part) => Number.parseInt(part, 10) || 0);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function openTab(url: string): void {
  window.open(url, "_blank", "noopener");
}

/** Haptics where the browser vibrates (Android); nothing elsewhere. */
function vibrate(pattern: number | number[]): void {
  navigator.vibrate?.(pattern);
}

/** The host's yes or no, handed to Telegram's callback; a dialog that broke is a no. */
function answered(answer: Promise<boolean>, callback: (yes: boolean) => void): void {
  void answer.then(callback, () => callback(false));
}

export function demoTelegram(host: DemoHost): TgWebApp {
  // Each listener once however often it subscribes, in the order they came: telegram-web-app.js's log.
  const listeners = new Map<string, Listener[]>();
  const on = (event: string, listener: Listener) => {
    const list = listeners.get(event) ?? [];
    if (!list.includes(listener)) listeners.set(event, [...list, listener]);
  };
  const off = (event: string, listener: Listener) => {
    listeners.set(event, (listeners.get(event) ?? []).filter((known) => known !== listener));
  };
  const emit = (event: string, data?: unknown) => {
    for (const listener of listeners.get(event) ?? []) listener(data);
  };

  const main: MainButtonState = { text: "", visible: false, active: true, progress: false };
  const showMain = () => host.mainButton({ ...main });
  let sharing = false;

  const user = { id: host.user.id, first_name: host.user.first_name, language_code: host.user.language_code };
  host.connect({
    // As telegram-web-app.js: a press of an inactive button never reaches the app.
    mainButtonClicked: () => {
      if (main.active) emit("mainButtonClicked");
    },
    backButtonClicked: () => emit("backButtonClicked"),
    themeChanged: () => emit("themeChanged"),
  });

  return {
    // Never signed: the demo's API does not read it, the app only needs it not empty.
    initData: `demo=1&user=${encodeURIComponent(JSON.stringify(user))}`,
    initDataUnsafe: { user },
    version: VERSION,
    get colorScheme() {
      return host.scheme();
    },
    isVersionAtLeast: (version) => compareVersions(VERSION, version) >= 0,
    ready: () => host.ready(),
    expand: () => undefined,
    disableVerticalSwipes: () => undefined,
    setHeaderColor: (color) => host.paint("header", color),
    setBackgroundColor: (color) => host.paint("background", color),
    setBottomBarColor: (color) => host.paint("bottom", color),
    enableClosingConfirmation: () => host.closingConfirmation(true),
    disableClosingConfirmation: () => host.closingConfirmation(false),
    showConfirm: (message, callback) => {
      answered(host.confirm(message), callback);
    },
    openLink: openTab,
    openTelegramLink: openTab,
    requestWriteAccess: (callback) => {
      answered(host.writeAccess(), (allowed) => callback?.(allowed));
    },
    shareMessage: (preparedId, callback) => {
      if (sharing) throw new Error("WebAppShareMessageOpened");
      sharing = true;
      answered(host.share(preparedId), (sent) => {
        sharing = false;
        // As telegram-web-app.js: the callback first, then the event, in the same turn.
        callback?.(sent);
        if (sent) emit("shareMessageSent");
        else emit("shareMessageFailed", { error: "USER_DECLINED" });
      });
    },
    onEvent: on,
    offEvent: off,
    BackButton: {
      show: () => host.backButton(true),
      hide: () => host.backButton(false),
      onClick: (callback) => on("backButtonClicked", callback),
      offClick: (callback) => off("backButtonClicked", callback),
    },
    MainButton: {
      setParams: (params) => {
        if (params.text !== undefined) main.text = params.text.trim();
        if (params.is_active !== undefined) main.active = params.is_active;
        if (params.is_visible !== undefined) main.visible = params.is_visible;
        showMain();
      },
      show: () => {
        main.visible = true;
        showMain();
      },
      hide: () => {
        main.visible = false;
        showMain();
      },
      showProgress: (leaveActive) => {
        main.active = Boolean(leaveActive);
        main.progress = true;
        showMain();
      },
      // As telegram-web-app.js: the end of the progress makes the button active again.
      hideProgress: () => {
        main.active = true;
        main.progress = false;
        showMain();
      },
      onClick: (callback) => on("mainButtonClicked", callback),
      offClick: (callback) => off("mainButtonClicked", callback),
    },
    HapticFeedback: {
      impactOccurred: () => vibrate(10),
      notificationOccurred: () => vibrate([10, 60, 10]),
      selectionChanged: () => vibrate(5),
    },
  };
}

/** Puts the stand-in where telegram-web-app.js puts Telegram's object. */
export function installTelegram(host: DemoHost): void {
  window.Telegram = { WebApp: demoTelegram(host) };
}
