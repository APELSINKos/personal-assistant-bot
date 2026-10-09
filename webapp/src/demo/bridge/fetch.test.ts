import { describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { ApiReply } from "./contract";
import { demoFetch } from "./fetch";
import { installTelegram } from "./telegram";
import { testHost } from "./testHost";

function ok(body: unknown): ApiReply {
  return { status: 200, body, headers: { "Content-Type": "application/json" } };
}

/** The same data as another page makes it: parsed by a frame of its own, in its own world. */
function foreign<T>(value: T): T {
  const frame = document.createElement("iframe");
  document.body.append(frame);
  const other = frame.contentWindow as unknown as typeof globalThis;
  const made = other.JSON.parse(JSON.stringify(value)) as T;
  frame.remove();
  return made;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

describe("the fetch bridge", () => {
  it("answers /api from the host with a Response of the frame's own", async () => {
    const answer = foreign({ city: "Москва", days: [1, 2] });
    expect(Object.getPrototypeOf(answer)).not.toBe(Object.prototype);
    const { host } = testHost(() => ok(answer));
    const response = await demoFetch(host, vi.fn())("/api/weather?city=3");
    expect(response).toBeInstanceOf(Response);
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("application/json");
    const data: unknown = await response.json();
    expect(data).toEqual({ city: "Москва", days: [1, 2] });
    expect(Object.getPrototypeOf(data)).toBe(Object.prototype);
  });

  it("hands the host the method, the path, the query and the JSON's text", async () => {
    const { host } = testHost(() => ok({}));
    await demoFetch(host, vi.fn())("/api/notes/11/items/31?x=1", { method: "PATCH", body: '{"done":true}' });
    expect(host.api).toHaveBeenCalledWith(
      { method: "PATCH", path: "/notes/11/items/31", search: "?x=1", body: '{"done":true}' },
    );
  });

  it("hands over a file as its name, type and size", async () => {
    const { host } = testHost(() => ok({}));
    const file = new File(["BEGIN:VCALENDAR"], "МИРЭА.ics", { type: "text/calendar" });
    await demoFetch(host, vi.fn())("/api/schedule/file?name=x", { method: "POST", body: file });
    expect(host.api.mock.calls[0]?.[0].body).toEqual({ file: "МИРЭА.ics", type: "text/calendar", size: 15 });
  });

  it("answers 204 without a body", async () => {
    const { host } = testHost(() => ({ status: 204, body: null, headers: {} }));
    const response = await demoFetch(host, vi.fn())("/api/notes/11", { method: "DELETE" });
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });

  it("rejects an aborted request with the frame's AbortError and never asks the host", async () => {
    const { host } = testHost(() => ok({}));
    const fetch = demoFetch(host, vi.fn());
    const before = new AbortController();
    before.abort();
    await expect(fetch("/api/me", { signal: before.signal })).rejects.toSatisfy(isAbort);
    const after = new AbortController();
    const pending = fetch("/api/me", { signal: after.signal });
    after.abort();
    await expect(pending).rejects.toSatisfy(isAbort);
    expect(host.api).not.toHaveBeenCalled();
  });

  it("leaves any other address to the browser", async () => {
    const { host } = testHost();
    const next = vi.fn(async () => new Response("body { }"));
    await demoFetch(host, next)("/assets/app.css");
    await demoFetch(host, next)("https://example.com/api/me");
    expect(next.mock.calls).toEqual([["/assets/app.css", undefined], ["https://example.com/api/me", undefined]]);
    expect(host.api).not.toHaveBeenCalled();
  });

  it("serves the app's own client, refusals too", async () => {
    const me = { id: 1, first_name: "Саша" };
    const stand = testHost((request) => (request.path === "/me" ? ok(me) : {
      status: 404,
      body: { type: "about:blank", title: "Not Found", status: 404, code: "not_found" },
      headers: { "Content-Type": "application/problem+json" },
    }));
    installTelegram(stand.host);
    vi.stubGlobal("fetch", demoFetch(stand.host, vi.fn()));
    await expect(api("/me")).resolves.toEqual(me);
    await expect(api("/habits/99")).rejects.toMatchObject({ status: 404, code: "not_found" });
  });
});
