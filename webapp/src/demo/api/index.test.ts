import { describe, expect, it } from "vitest";
import type { Me } from "../../api/types";
import type { ApiRequest } from "../bridge/contract";
import { createApi, ROUTES } from ".";
import { demoApi, MORNING } from "./testApi";

function get(path: string): ApiRequest {
  return { method: "GET", path, search: "", body: null };
}

/**
 * Every pair of method and path the app calls, with an everyday request of it and the status it
 * gets: in the order of the routers.
 */
const EVERYDAY: [string, unknown, number][] = [
  ["GET /health", undefined, 200],
  ["GET /me", undefined, 200],
  ["PATCH /me", { morning_time: "07:30" }, 200],
  ["POST /me/write-access", undefined, 200],
  ["GET /me/cities", undefined, 200],
  ["POST /me/cities", { name: "Сочи", admin: "Краснодарский край", country: "Россия", lat: 43.59917, lon: 39.72569, timezone: "Europe/Moscow", geo_id: 491422 }, 201],
  ["DELETE /me/cities/1", undefined, 204],
  ["PUT /me/city", { name: "Казань", lat: 55.78874, lon: 49.12214, timezone: "Europe/Moscow", geo_id: 551487 }, 200],
  ["GET /cities?q=%D0%9A%D0%B0%D0%B7", undefined, 200],
  ["GET /weather", undefined, 200],
  ["POST /weather/share?city=0", undefined, 200],
  ["POST /weather/card?city=2", undefined, 204],
  ["GET /today", undefined, 200],
  ["GET /notes", undefined, 200],
  ["POST /notes", { text: "Купить", items: ["хлеб"], pinned: false }, 201],
  ["PATCH /notes/2", { pinned: true }, 200],
  ["DELETE /notes/1", undefined, 204],
  ["POST /notes/4/items", { text: "носки" }, 201],
  ["PATCH /notes/4/items/5", { done: true }, 200],
  ["DELETE /notes/4/items/6", undefined, 204],
  ["DELETE /notes/4/items?done=true", undefined, 204],
  ["GET /reminders", undefined, 200],
  ["POST /reminders", { text: "Позвонить маме", due_local: "2026-10-07T19:00" }, 201],
  ["PATCH /reminders/2", { text: "Сдать лабу" }, 200],
  ["DELETE /reminders/3", undefined, 204],
  ["POST /reminders/parse", { text: "завтра в 9:30 купить молоко" }, 200],
  ["GET /agenda?from=2026-10-05&to=2026-10-11", undefined, 200],
  ["GET /habits", undefined, 200],
  ["POST /habits", { name: "Йога", emoji: "🧘", color: "sky", weekly_goal: 3 }, 201],
  ["GET /habits/1", undefined, 200],
  ["PATCH /habits/1", { color: "rose" }, 200],
  ["DELETE /habits/4", undefined, 204],
  ["PUT /habits/1/marks/2026-10-07", { done: true }, 200],
  ["POST /habits/1/share", undefined, 200],
  ["POST /habits/1/card", undefined, 204],
  ["GET /schedule", undefined, 200],
  ["GET /schedule/groups?q=%D0%98%D0%9A%D0%91%D0%9E", undefined, 200],
  ["PUT /schedule", { mirea_id: 4242 }, 200],
  ["POST /schedule/refresh", undefined, 200],
  ["PATCH /schedule", { lesson_reminder_minutes: 15 }, 200],
  ["DELETE /schedule", undefined, 204],
  ["GET /money?month=2026-10", undefined, 200],
  ["POST /money/entries", { amount: "250", category_id: 2, note: "кофе", day: "2026-10-07" }, 201],
  ["GET /money/entries/1", undefined, 200],
  ["PATCH /money/entries/1", { amount: "300" }, 200],
  ["DELETE /money/entries/1", undefined, 204],
  ["GET /money/categories", undefined, 200],
  ["POST /money/categories", { kind: "expense", name: "Кофейни", emoji: "☕" }, 201],
  ["PATCH /money/categories/1", { budget: "12000" }, 200],
  ["PUT /money/budget", { amount: "25000" }, 200],
  ["GET /rates/all", undefined, 200],
  ["GET /rates/history?code=USD", undefined, 200],
];

describe("the demo's API", () => {
  it("serves the app's 53 pairs of method and path, each once", () => {
    const pairs = ROUTES.map((route) => `${route.method} ${route.path}`);
    expect(new Set(pairs).size).toBe(pairs.length);
    expect(pairs).toHaveLength(53);
  });

  it("answers every pair with an everyday request as the server does", () => {
    const { call, api } = demoApi();
    for (const [request, body, status] of EVERYDAY) expect(call(request, body).status, request).toBe(status);
    const file = { method: "POST", path: "/schedule/file", search: "?name=demo.ics", body: { file: "demo.ics", type: "text/calendar", size: 900 } };
    expect(api(file).status).toBe(200);
    expect(EVERYDAY.length + 1).toBe(ROUTES.length);
  });

  it("writes its answers as JSON and its errors as problem+json", () => {
    const { call } = demoApi();
    expect(call("GET /me").headers).toEqual({ "Content-Type": "application/json" });
    expect(call("GET /habits/99")).toEqual({
      status: 404,
      body: { type: "about:blank", title: "Not found", status: 404, code: "not_found", entity: "habit" },
      headers: { "Content-Type": "application/problem+json" },
    });
  });

  it("answers a path it does not know with 404, a method it does not take with 405", () => {
    const api = createApi({ language: "ru", now: () => MORNING });
    expect(api(get("/rates"))).toEqual({
      status: 404,
      body: { type: "about:blank", title: "Not Found", status: 404, code: "not_found" },
      headers: { "Content-Type": "application/problem+json" },
    });
    expect(api({ method: "POST", path: "/reminders/1/done", search: "", body: null }).status).toBe(404);
    expect(api({ method: "DELETE", path: "/me", search: "", body: null })).toEqual({
      status: 405,
      body: { type: "about:blank", title: "Method Not Allowed", status: 405, code: "http_error" },
      headers: { "Content-Type": "application/problem+json" },
    });
    expect(api({ method: "PATCH", path: "/reminders/parse", search: "", body: "{}" }).body).toMatchObject({
      status: 422, field: "reminder_id",
    });
  });

  it("takes a body only as JSON or as a file, as the server does", () => {
    const api = createApi({ language: "ru", now: () => MORNING });
    expect(api({ method: "PATCH", path: "/me", search: "", body: "{" }).body).toMatchObject({
      status: 422, code: "validation_error", detail: "JSON decode error",
    });
    expect(api({ method: "PATCH", path: "/me", search: "", body: null }).body).toMatchObject({
      status: 422, detail: "Field required",
    });
    expect(api({ method: "PATCH", path: "/me", search: "", body: { file: "a.ics", type: "text/calendar", size: 3 } }).body)
      .toMatchObject({ status: 422, code: "validation_error" });
  });

  it("starts each visit afresh: a change lives in its own visit only", () => {
    const first = createApi({ language: "ru", now: () => MORNING });
    const second = createApi({ language: "ru", now: () => MORNING });
    first({ method: "PATCH", path: "/me", search: "", body: JSON.stringify({ currency: "EUR" }) });
    expect((first(get("/me")).body as Me).currency).toBe("EUR");
    expect((second(get("/me")).body as Me).currency).toBe("RUB");
  });

  it("runs on the clock it is given: Moscow's, moved by ?at=", () => {
    let now = MORNING;
    const api = createApi({ language: "en", now: () => now });
    expect(api(get("/today")).body).toMatchObject({ date: "2026-10-07", part_of_day: "morning" });
    now = Date.UTC(2026, 9, 6, 21, 30);
    expect(api(get("/today")).body).toMatchObject({ date: "2026-10-07", part_of_day: "night" });
  });
});
