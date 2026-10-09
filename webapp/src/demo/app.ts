/**
 * The app's page of the demo (app.html, spec §4.1): the three bridges go in first — the clock,
 * Telegram and fetch — and only then the app itself, unchanged. main comes by a dynamic import, so it
 * runs after them however the bundler splits the code into chunks: the modules it shares with the
 * host page would otherwise run first. Opened without its host page around it, app.html sends the
 * visitor there, on the same screen.
 */
import { installClock } from "./bridge/clock";
import { installFetch } from "./bridge/fetch";
import { hostAddress, parentHost } from "./bridge/frame";
import { installTelegram } from "./bridge/telegram";

const host = parentHost();
if (host) {
  installClock(host.clockOffset);
  installTelegram(host);
  installFetch(host);
  void import("../main");
} else {
  window.location.replace(hostAddress(window.location.hash));
}
