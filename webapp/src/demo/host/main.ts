/**
 * The demo's host page (index.html, spec §4.1, §6): the page around the unchanged app, which runs in
 * a frame of the same origin and finds the host as `window.parent.__demoHost`.
 */
// The app's own fonts and colours: the same files as the app's, shared by the two pages.
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/unbounded/700.css";
import "../../styles/tokens.css";
import "./host.css";
import { startDemo } from "./page";

startDemo(document.body, {
  address: { search: window.location.search, hash: window.location.hash },
  setAddress: (address) => window.history.replaceState(window.history.state, "", address),
  now: () => Date.now(),
  system: window.matchMedia("(prefers-color-scheme: dark)"),
  languages: navigator.languages.length > 0 ? navigator.languages : [navigator.language],
});
