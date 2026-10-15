/**
 * What the demo's two pages say to each other (spec §4.1). The app's frame asks the host page —
 * `window.parent.__demoHost` — for the language, the visitor, the clock, the theme and the API, and
 * hands it the state of Telegram's buttons, the dialogs and «Поделиться»; the host tells the frame
 * when a button is pressed or the theme changes. Only plain data crosses: an object made by one
 * page fails the other's `instanceof`, so a Response, a DOMException or a file is never handed
 * over — the side that needs one builds it from the data.
 */
import type { Lang } from "../../i18n";

export interface DemoUser {
  id: number;
  first_name: string;
  language_code: Lang;
}

/** Telegram's main button under the frame. */
export interface MainButtonState {
  text: string;
  visible: boolean;
  active: boolean;
  /** The spinner of a request under way. */
  progress: boolean;
}

/** A file the app sends — the calendar upload — as its name, type and size, never its bytes. */
export interface FileBody {
  file: string;
  type: string;
  size: number;
}

/** A request of the app to `/api…`. */
export interface ApiRequest {
  method: string;
  /** The path after /api, without the query: «/habits/7». */
  path: string;
  /** The query with its «?», or "". */
  search: string;
  /** The JSON the app sent, as its text; a file as its FileBody; null without a body. */
  body: string | FileBody | null;
}

/** The host's answer, of which the frame makes the Response. */
export interface ApiReply {
  status: number;
  /** What the JSON of the answer holds; nothing for 204. */
  body: unknown;
  headers: Record<string, string>;
}

/** What the host page tells the app's frame. */
export interface DemoFrame {
  mainButtonClicked(): void;
  backButtonClicked(): void;
  themeChanged(): void;
}

/** The host page, as the app's frame sees it. */
export interface DemoHost {
  readonly language: Lang;
  readonly user: DemoUser;
  /** How far the demo's clock runs ahead of the real one, in ms; null without `?at=`. */
  readonly clockOffset: number | null;
  scheme(): "dark" | "light";
  api(request: ApiRequest): ApiReply;
  /** A frame has started, the first time or after a reload: the host calls this one from now on. */
  connect(frame: DemoFrame): void;
  ready(): void;
  paint(part: "header" | "background" | "bottom", color: string): void;
  backButton(visible: boolean): void;
  mainButton(state: MainButtonState): void;
  closingConfirmation(enabled: boolean): void;
  confirm(message: string): Promise<boolean>;
  writeAccess(): Promise<boolean>;
  share(preparedId: string): Promise<boolean>;
}

/** The host page's window, where the frame finds the host. */
export interface HostWindow {
  __demoHost?: DemoHost;
}
