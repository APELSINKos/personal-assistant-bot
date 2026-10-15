import { expect } from "vitest";
import type { Lang } from "../../i18n";
import type { ApiReply } from "../bridge/contract";
import { serve } from ".";
import { visitOf } from "./data";
import { seed } from "./seeds";

/** Wednesday 7 October 2026, 10:30 in Moscow: the moment of the README's pictures. */
export const MORNING = Date.UTC(2026, 9, 7, 7, 30);

/**
 * The demo's API for a test, seeded at `at`: its visit to look into or change, its clock to move,
 * and its requests written as the app makes them — `call("PATCH /notes/3", { pinned: true })`.
 */
export function demoApi(language: Lang = "ru", at = MORNING) {
  let now = at;
  const visit = visitOf(seed(language, at), language, () => now);
  const api = serve(visit);
  const call = (request: string, body?: unknown): ApiReply => {
    const [method = "GET", address = "/"] = request.split(" ");
    const [path = "/", query] = address.split("?");
    return api({
      method, path, search: query === undefined ? "" : `?${query}`,
      body: body === undefined ? null : JSON.stringify(body),
    });
  };
  /** The answer's body of a request that has to succeed. */
  const read = <T>(request: string, body?: unknown): T => {
    const reply = call(request, body);
    if (reply.status >= 400) throw new Error(`${request}: ${reply.status} ${JSON.stringify(reply.body)}`);
    return reply.body as T;
  };
  return {
    visit, api, call, read,
    setNow: (moment: number) => {
      now = moment;
    },
  };
}

/** A problem+json the API answers with: the code and what follows it. */
export function problem(status: number, code: string, params: Record<string, unknown> = {}) {
  return {
    status,
    body: expect.objectContaining({ status, code, ...params }),
    headers: { "Content-Type": "application/problem+json" },
  };
}
