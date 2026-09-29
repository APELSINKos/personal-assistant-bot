import { vi } from "vitest";

export interface ApiCall {
  method: string;
  path: string;
  body: unknown;
}

type Reply = { status?: number; body?: unknown };
type Handler = (request: { method: string; path: string; body: unknown }) => Reply | undefined;

// A plain route value is either the JSON body itself, or a `{ status?, body? }` shape
// describing a non-200 response. None of the API payloads have a field literally named
// "body", so its presence is what tells the two apart.
function isReplyShape(value: unknown): value is Reply {
  return typeof value === "object" && value !== null && !Array.isArray(value) && "body" in value;
}

export function mockApi(routes: Record<string, unknown>) {
  const calls: ApiCall[] = [];
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input, "http://app.test");
    const method = init.method ?? "GET";
    const body: unknown = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    const path = url.pathname.replace(/^\/api/, "");
    calls.push({ method, path: path + url.search, body });
    const entry = routes[`${method} ${path}${url.search}`] ?? routes[`${method} ${path}`];
    if (entry === undefined) {
      return new Response(JSON.stringify({ status: 404, code: "not_found", title: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/problem+json" },
      });
    }
    const reply: Reply = typeof entry === "function"
      ? ((entry as Handler)({ method, path, body }) ?? {})
      : isReplyShape(entry)
        ? entry
        : { body: entry };
    const status = reply.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? null), {
      status,
      headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
