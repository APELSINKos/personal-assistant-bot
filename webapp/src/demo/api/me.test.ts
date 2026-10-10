import { describe, expect, it } from "vitest";
import type { City, Health, Me, WeatherCity } from "../../api/types";
import { version } from "../../../package.json";
import { demoApi, problem } from "./testApi";

describe("the profile (routers/me.py)", () => {
  it("GET /health: the app's version, no commit", () => {
    expect(demoApi().read<Health>("GET /health")).toEqual({ status: "ok", version, commit: null });
  });

  it("GET /me: Саша from Moscow, or Alex", () => {
    expect(demoApi().read<Me>("GET /me")).toEqual({
      id: 1, first_name: "Саша", language: "ru", language_setting: "auto",
      city: { name: "Москва", admin: null, country: null, lat: 55.75222, lon: 37.61556, timezone: "Europe/Moscow" },
      morning: { enabled: true, time: "08:00" }, can_write: true, currency: "RUB", money_budget: 3_000_000,
    });
    expect(demoApi("en").read<Me>("GET /me")).toMatchObject({ first_name: "Alex", language: "en", city: { name: "Moscow" } });
  });

  it("PATCH /me: the language, the morning digest and the currency — any of the settings' sixteen", () => {
    const { read, call } = demoApi();
    expect(read<Me>("PATCH /me", { language: "en" })).toMatchObject({ language: "en", language_setting: "en" });
    expect(read<Me>("PATCH /me", { language: "auto" })).toMatchObject({ language: "ru", language_setting: "auto" });
    expect(read<Me>("PATCH /me", { morning_enabled: false, morning_time: "7:5" })).toMatchObject({
      morning: { enabled: false, time: "07:05" },
    });
    for (const currency of ["UAH", "UZS", "KGS", "GEL", "AZN", "TJS", "PLN", "RUB"]) {
      expect(read<Me>("PATCH /me", { currency }).currency).toBe(currency);
    }
    expect(call("PATCH /me", { morning_time: "24:00" })).toEqual(problem(422, "validation_error", { field: "time", reason: "format" }));
    expect(call("PATCH /me", { currency: "XAU" })).toEqual(
      problem(422, "validation_error", { field: "currency", reason: "unsupported" }),
    );
    expect(call("PATCH /me", { currency: "RUBL" })).toEqual(problem(422, "validation_error", { field: "currency", limit: 3 }));
    expect(call("PATCH /me", { language: "de" })).toEqual(problem(422, "validation_error", { field: "language" }));
    expect(read<Me>("GET /me")).toMatchObject({ morning: { enabled: false, time: "07:05" }, currency: "RUB" });
  });

  it("POST /me/write-access: the bot may write", () => {
    const { visit, read } = demoApi();
    visit.data.profile.can_write = false;
    expect(read<Me>("POST /me/write-access").can_write).toBe(true);
  });
});

describe("the cities (routers/me.py, services/cities.py)", () => {
  it("GET /cities: about twenty places in both languages, named in the user's", () => {
    const { read, call } = demoApi();
    expect(read<City[]>(`GET /cities?q=${encodeURIComponent("моск")}`)).toEqual([
      { name: "Москва", admin: "Москва", country: "Россия", lat: 55.75222, lon: 37.61556, timezone: "Europe/Moscow", geo_id: 524901 },
    ]);
    expect(read<City[]>("GET /cities?q=kamch").map((city) => city.name)).toEqual(["Петропавловск-Камчатский"]);
    expect(demoApi("en").read<City[]>(`GET /cities?q=${encodeURIComponent("ере")}`)).toEqual([
      expect.objectContaining({ name: "Yerevan", country: "Armenia", timezone: "Asia/Yerevan" }),
    ]);
    expect(read<City[]>("GET /cities?q=Gotham")).toEqual([]);
    expect(call(`GET /cities?q=${encodeURIComponent("М")}`)).toEqual(problem(422, "validation_error", { field: "q", limit: 2 }));
    expect(call("GET /cities")).toEqual(problem(422, "validation_error", { field: "q", detail: "Field required" }));
  });

  it("GET /me/cities: Тула, Петропавловск-Камчатский and Ереван", () => {
    expect(demoApi().read<WeatherCity[]>("GET /me/cities")).toEqual([
      { id: 1, name: "Тула", admin: "Тульская область", country: "Россия", lat: 54.19609, lon: 37.61822, timezone: "Europe/Moscow", geo_id: 480562 },
      expect.objectContaining({ id: 2, name: "Петропавловск-Камчатский", timezone: "Asia/Kamchatka" }),
      expect.objectContaining({ id: 3, name: "Ереван", timezone: "Asia/Yerevan" }),
    ]);
  });

  it("POST /me/cities: a found place, up to four, never twice and never the home", () => {
    const { read, call } = demoApi();
    const [sochi] = read<City[]>(`GET /cities?q=${encodeURIComponent("соч")}`);
    const added = call("POST /me/cities", sochi);
    expect(added.status).toBe(201);
    expect(added.body).toEqual({ id: 4, ...sochi });
    const [berlin] = read<City[]>("GET /cities?q=berlin");
    expect(call("POST /me/cities", berlin)).toEqual(problem(409, "limit_reached", { entity: "city", limit: 4 }));
    call("DELETE /me/cities/4");
    expect(call("POST /me/cities", read<City[]>("GET /cities?q=tula")[0])).toEqual(
      problem(422, "validation_error", { field: "city", reason: "duplicate" }),
    );
    expect(call("POST /me/cities", read<City[]>("GET /cities?q=moscow")[0])).toEqual(
      problem(422, "validation_error", { field: "city", reason: "duplicate" }),
    );
    expect(call("POST /me/cities", { ...berlin, timezone: "Europe/Atlantis" })).toEqual(
      problem(422, "validation_error", { field: "city", reason: "invalid" }),
    );
    expect(call("POST /me/cities", { ...berlin, lat: 91 })).toEqual(problem(422, "validation_error", { field: "lat", limit: 90 }));
    expect(call("POST /me/cities", berlin).status).toBe(201);
  });

  it("DELETE /me/cities/{city_id}: gone, then 404", () => {
    const { read, call } = demoApi();
    expect(call("DELETE /me/cities/2")).toEqual({ status: 204, body: null, headers: {} });
    expect(read<WeatherCity[]>("GET /me/cities").map((city) => city.id)).toEqual([1, 3]);
    expect(call("DELETE /me/cities/2")).toEqual(problem(404, "not_found", { entity: "city" }));
    expect(call("DELETE /me/cities/x")).toEqual(problem(422, "validation_error", { field: "city_id" }));
  });

  it("PUT /me/city: a new home, which leaves the extra cities", () => {
    const { read, call } = demoApi();
    const [tula] = read<City[]>("GET /cities?q=tula");
    const me = read<Me>("PUT /me/city", { name: tula?.name, lat: tula?.lat, lon: tula?.lon, timezone: tula?.timezone, geo_id: tula?.geo_id });
    expect(me.city).toEqual({ name: "Тула", admin: null, country: null, lat: 54.19609, lon: 37.61822, timezone: "Europe/Moscow" });
    expect(read<WeatherCity[]>("GET /me/cities").map((city) => city.name)).toEqual(["Петропавловск-Камчатский", "Ереван"]);
    expect(call("PUT /me/city", { name: " ", lat: 1, lon: 1, timezone: "Europe/Moscow" })).toEqual(
      problem(422, "validation_error", { field: "city", reason: "invalid" }),
    );
    expect(call("PUT /me/city", { name: "X", lat: 1, lon: 1 })).toEqual(problem(422, "validation_error", { field: "timezone" }));
  });
});
