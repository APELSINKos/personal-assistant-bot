import { describe, expect, it } from "vitest";
import type { ApiRequest } from "../bridge/contract";
import { createApi } from ".";

const NOW = Date.UTC(2026, 9, 7, 7, 30); // 10:30 on Wednesday, October 7, in Moscow

function get(path: string): ApiRequest {
  return { method: "GET", path, search: "", body: null };
}

describe("the demo's API, as a stand-in for now", () => {
  it("knows the visitor: Саша from Москва, or Alex from Moscow", () => {
    const ru = createApi({ language: "ru", now: () => NOW })(get("/me"));
    expect(ru.status).toBe(200);
    expect(ru.body).toMatchObject({
      id: 1, first_name: "Саша", language: "ru", language_setting: "auto",
      city: { name: "Москва", timezone: "Europe/Moscow" }, can_write: true, currency: "RUB",
    });
    const en = createApi({ language: "en", now: () => NOW })(get("/me"));
    expect(en.body).toMatchObject({ first_name: "Alex", language: "en", city: { name: "Moscow" } });
  });

  it("gives the day on Moscow's clock", () => {
    const morning = createApi({ language: "ru", now: () => NOW })(get("/today"));
    expect(morning.status).toBe(200);
    expect(morning.body).toMatchObject({ date: "2026-10-07", part_of_day: "morning" });
    const night = createApi({ language: "ru", now: () => Date.UTC(2026, 9, 6, 21, 30) })(get("/today"));
    expect(night.body).toMatchObject({ date: "2026-10-07", part_of_day: "night" });
  });

  it("answers anything else as the server answers an unknown path", () => {
    expect(createApi({ language: "ru", now: () => NOW })(get("/habits"))).toEqual({
      status: 404,
      body: { type: "about:blank", title: "Not Found", status: 404, code: "not_found" },
      headers: { "Content-Type": "application/problem+json" },
    });
  });
});
