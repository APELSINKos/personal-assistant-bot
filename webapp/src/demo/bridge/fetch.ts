/**
 * The app's fetch in the demo's frame (spec §4.1): a request to `/api…` — the app's only one — goes
 * to the host page's API as plain data, and the answer comes back as a Response made here, in the
 * frame's own world, as is the AbortError of a cancelled request. Any other address goes on to the
 * browser as it would (and meets the page's `connect-src 'none'`).
 */
import type { ApiReply, ApiRequest, DemoHost } from "./contract";

const API = "/api";

/** The statuses whose Response has no body at all. */
const NO_BODY = new Set([204, 205, 304]);

/** The app's request body as plain data: JSON stays its text, a file becomes what it is. */
function plainBody(body: BodyInit | null | undefined): ApiRequest["body"] {
  if (body === undefined || body === null) return null;
  if (typeof body === "string") return body;
  if (body instanceof Blob) return { file: body instanceof File ? body.name : "", type: body.type, size: body.size };
  throw new TypeError("The demo's API takes JSON or a file");
}

function toResponse(reply: ApiReply): Response {
  const body = NO_BODY.has(reply.status) ? null : JSON.stringify(reply.body ?? null);
  return new Response(body, { status: reply.status, headers: { ...reply.headers } });
}

/** The API's address in the request, or null when it is some other address. */
function apiAddress(input: RequestInfo | URL): URL | null {
  if (typeof input !== "string" && !(input instanceof URL)) return null;
  const address = new URL(input, window.location.href);
  const own = address.origin === window.location.origin;
  return own && (address.pathname === API || address.pathname.startsWith(`${API}/`)) ? address : null;
}

export function demoFetch(host: DemoHost, next: typeof fetch): typeof fetch {
  return async (input, init) => {
    const address = apiAddress(input);
    if (!address) return next(input, init);
    const request: ApiRequest = {
      method: (init?.method ?? "GET").toUpperCase(),
      path: address.pathname.slice(API.length) || "/",
      search: address.search,
      body: plainBody(init?.body),
    };
    // A fetch never answers in the turn it was made, so an abort right after it still counts.
    await Promise.resolve();
    if (init?.signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
    return toResponse(host.api(request));
  };
}

/** Puts the bridge in place of the frame's fetch. */
export function installFetch(host: DemoHost): void {
  window.fetch = demoFetch(host, window.fetch.bind(window));
}
