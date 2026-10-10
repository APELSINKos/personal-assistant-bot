import { describe, expect, it } from "vitest";
import type { City, Forecast, SharedCard, WeatherCity } from "../../api/types";
import { PLACES, placeOut } from "./places";
import { demoApi, problem } from "./testApi";

const WORDS_RU = ["ясно", "малооблачно", "пасмурно", "туман", "морось", "дождь", "снег", "ливень", "снегопад", "гроза"];

describe("the weather (routers/weather.py)", () => {
  it("GET /weather: the home city's forecast on its clock — now, 23 hours, 7 days, the sun", () => {
    const forecast = demoApi().read<Forecast>("GET /weather");
    expect(forecast.city).toEqual({ id: 0, name: "Москва", home: true });
    expect(forecast.now).toEqual({
      temperature: expect.any(Number), feels_like: expect.any(Number), wind: expect.any(Number),
      gusts: expect.any(Number), humidity: expect.any(Number), is_day: true, emoji: expect.any(String),
      description: expect.any(String), precip_chance: expect.any(Number),
    });
    expect(WORDS_RU).toContain(forecast.now.description);
    expect(forecast.tips.length).toBeGreaterThan(0);
    expect(forecast.hours).toHaveLength(23);
    expect(forecast.hours[0]).toMatchObject({ time: "11:00", temperature: expect.any(Number) });
    expect(forecast.hours[22]?.time).toBe("09:00");
    expect(forecast.days.map((day) => day.date)).toEqual([
      "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13",
    ]);
    for (const day of forecast.days) {
      expect(day.tmin).toBeLessThanOrEqual(day.tmax);
      expect(WORDS_RU).toContain(day.description);
    }
    // Moscow on 7 October: the sun rises about 07:00 and sets about 17:50.
    expect(forecast.sunrise).toMatch(/^0[67]:\d{2}$/);
    expect(forecast.sunset).toMatch(/^17:[45]\d$/);
    expect(forecast.polar).toBeNull();
  });

  it("GET /weather?city=N: an extra city on its own clock, 404 for one that is not there", () => {
    const { read, call } = demoApi();
    const kamchatka = read<Forecast>("GET /weather?city=2");
    expect(kamchatka.city).toEqual({ id: 2, name: "Петропавловск-Камчатский", home: false });
    expect(kamchatka.hours[0]?.time).toBe("20:00");
    expect(kamchatka.days[0]?.date).toBe("2026-10-07");
    expect(read<Forecast>("GET /weather?city=0").city.home).toBe(true);
    expect(call("GET /weather?city=9")).toEqual(problem(404, "not_found", { entity: "city" }));
    expect(call("GET /weather?city=x")).toEqual(problem(422, "validation_error", { field: "city" }));
    expect(call("GET /weather?city=-1")).toEqual(problem(422, "validation_error", { field: "city", limit: 0 }));
  });

  it("gives a place its own weather: wherever it stands in the list, and as the home too", () => {
    const { read, call } = demoApi();
    // A forecast without its label: the home city is shown as the home, an extra one by its id.
    const sky = (forecast: Forecast) => ({ ...forecast, city: null });
    const moscow = read<Forecast>("GET /weather");
    const kamchatka = read<Forecast>("GET /weather?city=2");
    const yerevan = read<Forecast>("GET /weather?city=3");
    expect(call("DELETE /me/cities/1").status).toBe(204);
    expect(read<Forecast>("GET /weather?city=2")).toEqual(kamchatka);
    expect(read<Forecast>("GET /weather?city=3")).toEqual(yerevan);
    // Ереван becomes the home, Москва an extra city: each keeps its weather.
    const [found] = read<City[]>("GET /cities?q=ереван");
    read("PUT /me/city", { name: found?.name, lat: found?.lat, lon: found?.lon, timezone: found?.timezone, geo_id: found?.geo_id });
    expect(sky(read<Forecast>("GET /weather"))).toEqual(sky(yerevan));
    const added = read<WeatherCity>("POST /me/cities", read<City[]>("GET /cities?q=москва")[0]);
    expect(sky(read<Forecast>(`GET /weather?city=${added.id}`))).toEqual(sky(moscow));
  });

  it("gives any other place of the search weather of its own, not a copy of a city on the list", () => {
    // What a place's pattern of days decides: the wind, the gusts, the humidity, the week's chances.
    const ofPattern = (forecast: Forecast) => JSON.stringify([
      forecast.now.wind, forecast.now.gusts, forecast.now.humidity, forecast.days.map((day) => day.precip_chance),
    ]);
    const { read } = demoApi();
    const seeded = ["GET /weather", "GET /weather?city=1", "GET /weather?city=2", "GET /weather?city=3"]
      .map((request) => read<Forecast>(request));
    const story = seeded.map((forecast) => forecast.city.name);
    const others = PLACES.filter((place) => !story.includes(place.ru[0]));
    expect(others).toHaveLength(PLACES.length - 4);
    // Each one added as the fourth city: the seeded three leave room for one more.
    const repeats = others.flatMap((place) => {
      const fourth = demoApi();
      const added = fourth.read<WeatherCity>("POST /me/cities", placeOut(place, "ru"));
      const own = ofPattern(fourth.read<Forecast>(`GET /weather?city=${added.id}`));
      return seeded
        .filter((forecast) => ofPattern(forecast) === own)
        .map((forecast) => `${place.ru[0]} = ${forecast.city.name}`);
    });
    expect(repeats).toEqual([]);
  });

  it("holds together: the same moment gives the same weather, in the user's words", () => {
    const { read } = demoApi();
    expect(read<Forecast>("GET /weather?city=3")).toEqual(read<Forecast>("GET /weather?city=3"));
    read("PATCH /me", { language: "en" });
    expect(read<Forecast>("GET /weather").now.description).toMatch(/^[a-z ]+$/);
  });

  it("follows the seasons: January in Moscow below zero, July above +15", () => {
    const mean = (forecast: Forecast) => forecast.days.map((day) => (day.tmin + day.tmax) / 2);
    const january = demoApi("ru", Date.UTC(2027, 0, 15, 9, 0)).read<Forecast>("GET /weather");
    expect(Math.max(...mean(january))).toBeLessThan(0);
    expect(january.days.some((day) => day.description === "снег" || day.description === "снегопад")).toBe(true);
    const july = demoApi("ru", Date.UTC(2027, 6, 15, 9, 0)).read<Forecast>("GET /weather");
    expect(Math.min(...mean(july))).toBeGreaterThan(15);
  });
});

describe("the forecast as a picture (routers/weather.py)", () => {
  it("POST /weather/share?city=N: a prepared message of the city's week; 404 for a city not there", () => {
    const { read, call } = demoApi();
    expect(read<SharedCard>("POST /weather/share?city=0")).toEqual({ prepared_id: "demo-forecast-0-1" });
    expect(read<SharedCard>("POST /weather/share?city=2")).toEqual({ prepared_id: "demo-forecast-2-2" });
    expect(call("POST /weather/share?city=7")).toEqual(problem(404, "not_found", { entity: "city" }));
  });

  it("POST /weather/card?city=N: sent to the chat with the bot, if the bot may write", () => {
    const { visit, call } = demoApi();
    expect(call("POST /weather/card?city=3")).toEqual({ status: 204, body: null, headers: {} });
    expect(call("POST /weather/card?city=7")).toEqual(problem(404, "not_found", { entity: "city" }));
    visit.data.profile.can_write = false;
    expect(call("POST /weather/card?city=0")).toEqual({
      status: 403,
      body: {
        type: "about:blank", title: "The bot may not write to the user", status: 403, code: "write_forbidden",
      },
      headers: { "Content-Type": "application/problem+json" },
    });
  });
});
