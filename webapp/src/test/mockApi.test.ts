import { describe, expect, it } from "vitest";
import { mockApi } from "./mockApi";

describe("mockApi", () => {
  it("treats a status-only route value as a reply with no body", async () => {
    mockApi({ "DELETE /notes/11": { status: 204 } });
    const response = await fetch("/api/notes/11", { method: "DELETE" });
    expect(response.status).toBe(204);
  });

  it("still treats a real payload that happens to have a numeric-looking status as the body", async () => {
    // /health's payload has a string "status" plus other fields — never a reply shape.
    mockApi({ "GET /health": { status: "ok", version: "1.0.0", commit: null } });
    const response = await fetch("/api/health");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok", version: "1.0.0", commit: null });
  });

  it("still supports a plain JSON body with no status/body wrapper", async () => {
    mockApi({ "GET /me": { id: 1, language: "en" } });
    const response = await fetch("/api/me");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ id: 1, language: "en" });
  });

  it("still supports the explicit { status, body } shape", async () => {
    mockApi({ "GET /me": { status: 401, body: { code: "expired_init_data" } } });
    const response = await fetch("/api/me");
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ code: "expired_init_data" });
  });

  it("still supports a function handler", async () => {
    mockApi({ "POST /notes": () => ({ status: 201, body: { id: 5 } }) });
    const response = await fetch("/api/notes", { method: "POST", body: "{}" });
    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toEqual({ id: 5 });
  });
});
