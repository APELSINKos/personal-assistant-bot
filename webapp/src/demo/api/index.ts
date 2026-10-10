/**
 * The demo's API in the host page (spec §5): it answers the app's requests from memory, as the
 * routers of src/assistant/api answer them on the server — the same paths, the app's own types
 * (src/api/types.ts) for every answer, the server's limits and errors as problem+json. Each section
 * is a module of its own; this one holds the table of routes and picks the route of a request, as
 * Starlette's router does.
 */
import type { Lang } from "../../i18n";
import type { ApiReply, ApiRequest } from "../bridge/contract";
import { visitOf, type Visit } from "./data";
import { HABITS } from "./habits";
import { invalidInput, match, Problem, problemReply, type Route } from "./http";
import { ME } from "./me";
import { MONEY } from "./money";
import { NOTES } from "./notes";
import { RATES } from "./rates";
import { REMINDERS } from "./reminders";
import { SCHEDULE } from "./schedule";
import { seed } from "./seeds";
import { TODAY } from "./today";
import { WEATHER } from "./weather";

export interface ApiOptions {
  language: Lang;
  /** The demo's clock: the real one, or the one `?at=` moved. */
  now: () => number;
}

export type DemoApi = (request: ApiRequest) => ApiReply;

/** Every route of the API: the pairs of method and path the app calls (coverage.test.ts holds them to it). */
export const ROUTES: readonly Route[] = [
  ...ME, ...WEATHER, ...TODAY, ...NOTES, ...REMINDERS, ...HABITS, ...SCHEDULE, ...MONEY, ...RATES,
];

/** The body as FastAPI reads it before anything else: JSON, else a refusal; a file as it came. */
function readBody(body: ApiRequest["body"]): unknown {
  if (body === null) return undefined;
  if (typeof body !== "string") return body;
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw invalidInput({ detail: "JSON decode error" });
  }
}

/** The answer to a request: the first route of its path and method; 405 for another method, 404 for no path. */
function answer(visit: Visit, request: ApiRequest): ApiReply {
  const routes = ROUTES.flatMap((route) => {
    const params = match(route.path, request.path);
    return params ? [{ route, params }] : [];
  });
  const found = routes.find(({ route }) => route.method === request.method);
  try {
    if (!found) {
      throw routes.length
        ? new Problem(405, "http_error", "Method Not Allowed")
        : new Problem(404, "not_found", "Not Found");
    }
    const body = readBody(request.body);
    return found.route.answer(visit, { params: found.params, query: new URLSearchParams(request.search), body });
  } catch (error) {
    if (error instanceof Problem) return problemReply(error);
    // As errors.py answers what it did not foresee; the browser's console tells what it was.
    console.error(`${request.method} ${request.path}:`, error);
    return problemReply(new Problem(500, "internal_error", "Internal server error"));
  }
}

/** The API of a visit: its answers change only its data. */
export function serve(visit: Visit): DemoApi {
  return (request) => answer(visit, request);
}

/** A new visit's API, seeded in the language the demo is opened in. */
export function createApi({ language, now }: ApiOptions): DemoApi {
  return serve(visitOf(seed(language, now()), language, now));
}
