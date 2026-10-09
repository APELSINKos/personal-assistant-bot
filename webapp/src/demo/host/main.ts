/**
 * The demo's host page (index.html, spec §4.1): it keeps what Telegram keeps outside the app — the
 * language, the visitor, the clock, the theme and the API — and holds the unchanged app in a frame
 * of the same origin, which finds all of it as `window.parent.__demoHost`. Telegram's chrome around
 * the frame is not drawn yet: the frame fills the page, the browser asks the app's questions and
 * the dialogs that have no stand-in answer no.
 */
import "./host.css";
import { resolveLang, type Lang } from "../../i18n";
import { createApi } from "../api";
import { parseAt } from "../api/clock";
import { WORDS as DATA } from "../api/words";
import type { DemoFrame, DemoHost, HostWindow } from "../bridge/contract";
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

// ?theme= or the system's; until the visitor picks one, the theme follows the system.
const themed = query.get("theme");
const system = window.matchMedia("(prefers-color-scheme: dark)");
let scheme: "dark" | "light" = themed === "dark" || themed === "light" ? themed : system.matches ? "dark" : "light";
let frame: DemoFrame | null = null;
if (themed !== "dark" && themed !== "light") {
  system.addEventListener("change", () => {
    scheme = system.matches ? "dark" : "light";
    frame?.themeChanged();
  });
}

const host: DemoHost = {
  language,
  user: { id: 1, first_name: DATA[language].name, language_code: language },
  clockOffset,
  scheme: () => scheme,
  api: createApi({ language, now: () => Date.now() + (clockOffset ?? 0) }),
  connect: (next) => {
    frame = next;
  },
  ready: () => undefined,
  paint: () => undefined,
  backButton: () => undefined,
  mainButton: () => undefined,
  closingConfirmation: () => undefined,
  confirm: (message) => Promise.resolve(window.confirm(message)),
  writeAccess: () => Promise.resolve(false),
  share: () => Promise.resolve(false),
};
(window as unknown as HostWindow).__demoHost = host;

document.documentElement.lang = language;
document.title = WORDS[language].title;
const app = document.createElement("iframe");
app.className = "demo-frame";
app.title = WORDS[language].frame;
app.src = `./app.html${window.location.hash.startsWith("#/") ? window.location.hash : "#/"}`;
document.body.append(app);
