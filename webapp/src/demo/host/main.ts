/**
 * The demo's host page (index.html, spec §4.1): it keeps what Telegram keeps outside the app — the
 * language, the visitor, the clock, the theme and the API — and draws Telegram's chrome around the
 * unchanged app, which runs in a frame of the same origin and finds all of it as
 * `window.parent.__demoHost`.
 */
// The app's own fonts and colours: the same files as the app's, shared by the two pages.
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "../../styles/tokens.css";
import "./host.css";
import { resolveLang, type Lang } from "../../i18n";
import { createApi } from "../api";
import { parseAt } from "../api/clock";
import { WORDS as DATA } from "../api/words";
import type { DemoHost, HostWindow } from "../bridge/contract";
import { createDevice } from "./device";
import { WORDS } from "./words";

const query = new URLSearchParams(window.location.search);

function pickLanguage(): Lang {
  const asked = query.get("lang");
  if (asked === "ru" || asked === "en") return asked;
  return resolveLang(navigator.languages[0] ?? navigator.language);
}

const language = pickLanguage();
const at = parseAt(query.get("at"));
const clockOffset = at === null ? null : at - Date.now();

const device = createDevice({ language: () => language, words: () => WORDS[language] });

// ?theme= or the system's; until the visitor picks one, the theme follows the system.
const themed = query.get("theme");
const system = window.matchMedia("(prefers-color-scheme: dark)");
let scheme: "dark" | "light" = themed === "dark" || themed === "light" ? themed : system.matches ? "dark" : "light";
if (themed !== "dark" && themed !== "light") {
  system.addEventListener("change", () => {
    scheme = system.matches ? "dark" : "light";
    document.documentElement.dataset.theme = scheme;
    device.frame()?.themeChanged();
  });
}

const host: DemoHost = {
  language,
  user: { id: 1, first_name: DATA[language].name, language_code: language },
  clockOffset,
  scheme: () => scheme,
  api: createApi({ language, now: () => Date.now() + (clockOffset ?? 0) }),
  ...device.chrome,
};
(window as unknown as HostWindow).__demoHost = host;

document.documentElement.lang = language;
document.documentElement.dataset.theme = scheme;
document.title = WORDS[language].title;
document.body.append(device.element);
device.open(window.location.hash.startsWith("#/") ? window.location.hash.slice(1) : "/");
