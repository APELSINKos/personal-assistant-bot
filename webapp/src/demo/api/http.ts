/**
 * The demo's API as HTTP (src/assistant/api/errors.py and FastAPI's routing): the answers, every
 * error as application/problem+json with the API's own code, and the routes, written as the
 * routers write their paths.
 */
import type { ApiReply } from "../bridge/contract";
import type { Visit } from "./data";

type Param = string | number | boolean | undefined;

/** An error the API answers with: errors.py's problem(). */
export class Problem extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  /** What goes into the body after the code: detail, field, reason, limit, entity, service. */
  readonly params: Record<string, Param>;

  constructor(status: number, code: string, title: string, params: Record<string, Param> = {}) {
    super(code);
    this.name = "Problem";
    this.status = status;
    this.code = code;
    this.title = title;
    this.params = params;
  }
}

/** core/errors.py's InvalidInput, and FastAPI's RequestValidationError as errors.py words it. */
export const invalidInput = (params: Record<string, Param>) => new Problem(422, "validation_error", "Invalid input", params);
export const notFound = (entity: string) => new Problem(404, "not_found", "Not found", { entity });
export const limitReached = (entity: string, limit: number) =>
  new Problem(409, "limit_reached", "Limit reached", { entity, limit });
export const writeForbidden = () => new Problem(403, "write_forbidden", "The bot may not write to the user");

/** The problem+json of an error: type, title, status and code, then its params. */
export function problemReply(problem: Problem): ApiReply {
  const body: Record<string, unknown> = {
    type: "about:blank", title: problem.title, status: problem.status, code: problem.code,
  };
  for (const [key, value] of Object.entries(problem.params)) if (value !== undefined) body[key] = value;
  return { status: problem.status, body, headers: { "Content-Type": "application/problem+json" } };
}

/** An answer of the API, typed as the app reads it: `json<Note[]>(…)`. */
export function json<T>(body: T, status = 200): ApiReply {
  return { status, body, headers: { "Content-Type": "application/json" } };
}

export const created = <T>(body: T): ApiReply => json(body, 201);

export const noContent = (): ApiReply => ({ status: 204, body: null, headers: {} });

/** A request as a route reads it. */
export interface Call {
  /** The parameters of the path by their names in the route: {note_id: "7"}. */
  params: Record<string, string>;
  query: URLSearchParams;
  /** The JSON the app sent; a file as its FileBody; undefined without a body. */
  body: unknown;
}

export interface Route {
  method: string;
  /** As the router writes it: "/notes/{note_id}/items". */
  path: string;
  answer: (visit: Visit, call: Call) => ApiReply;
}

export function route(method: string, path: string, answer: Route["answer"]): Route {
  return { method, path, answer };
}

/** The parameters of a path the route's path matches, or null: a parameter is one whole part. */
export function match(template: string, path: string): Record<string, string> | null {
  const want = template.split("/");
  const have = path.split("/");
  if (want.length !== have.length) return null;
  const params: Record<string, string> = {};
  for (const [index, part] of want.entries()) {
    const value = have[index] ?? "";
    if (part.startsWith("{") && part.endsWith("}")) {
      if (!value) return null;
      try {
        params[part.slice(1, -1)] = decodeURIComponent(value);
      } catch {
        return null;
      }
    } else if (part !== value) {
      return null;
    }
  }
  return params;
}
