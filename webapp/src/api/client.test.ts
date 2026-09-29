import { describe, expect, it, vi } from "vitest";
import { installTelegram } from "../test/fakeTelegram";
import { AUTH_EXPIRED_EVENT, ApiError, api } from "./client";

function respond(status: number, body?: unknown) {
  return vi.fn(async () =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
    }),
  );
}

describe("api client", () => {
  it("sends the Telegram signature and JSON", async () => {
    installTelegram();
    const fetchMock = respond(201, { id: 1, text: "x" });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api("/notes", { method: "POST", body: { text: "x" } })).resolves.toEqual({ id: 1, text: "x" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/notes");
    expect((init.headers as Record<string, string>).Authorization).toMatch(/^tma query_id=/);
    expect(init.body).toBe('{"text":"x"}');
  });

  it("returns nothing for 204", async () => {
    installTelegram();
    vi.stubGlobal("fetch", respond(204));
    await expect(api("/notes/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("turns problems into ApiError", async () => {
    installTelegram();
    vi.stubGlobal("fetch", respond(422, {
      type: "about:blank", title: "Invalid input", status: 422, code: "validation_error",
      field: "when", reason: "past",
    }));
    const error = await api("/reminders", { method: "POST", body: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("validation_error");
    expect((error as ApiError).reason).toBe("past");
  });

  it("announces an expired session on 401 and outside Telegram", async () => {
    const seen = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, seen);
    installTelegram();
    vi.stubGlobal("fetch", respond(401, { code: "expired_init_data", status: 401, title: "Unauthorized" }));
    await expect(api("/me")).rejects.toMatchObject({ status: 401, code: "expired_init_data" });
    window.Telegram = undefined;
    await expect(api("/me")).rejects.toMatchObject({ status: 401, code: "no_init_data" });
    expect(seen).toHaveBeenCalledTimes(2);
    window.removeEventListener(AUTH_EXPIRED_EVENT, seen);
  });

  it("reports a network failure", async () => {
    installTelegram();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(api("/me")).rejects.toMatchObject({ status: 0, code: "network" });
  });
});
