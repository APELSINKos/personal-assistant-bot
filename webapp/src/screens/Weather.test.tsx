import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Forecast } from "../api/types";
import { Toasts } from "../components/Toasts";
import type { Lang } from "../i18n";
import { NBSP } from "../lib/money";
import { installTelegram } from "../test/fakeTelegram";
import { forecast, me, tula } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { WeatherScreen } from "./Weather";

const TULA: Forecast = {
  ...forecast,
  city: { id: 3, name: "Тула", home: false },
  now: { ...forecast.now, temperature: 7.4 },
};
const UNAVAILABLE = {
  status: 503, body: { status: 503, code: "upstream_unavailable", title: "Upstream service unavailable" },
};
const GONE = { status: 404, body: { status: 404, code: "not_found", title: "Not found" } };

function renderWeather(path = "/weather", lang: Lang = "ru") {
  return renderWithApp(<><WeatherScreen /><Toasts /></>, { path, lang });
}

// The visible text is matched as Testing Library normalises it, with a plain space where the app
// keeps a percent on the number's line with a no-break one; accessible names keep NBSP.

/** The card a heading names. */
function cardOf(name: string): HTMLElement {
  const card = screen.getByRole("heading", { name }).closest("section");
  if (!card) throw new Error(`no card ${name}`);
  return card;
}

/** A pull down the screen far enough to refresh it. */
function pullDown() {
  const title = screen.getByRole("heading", { level: 1 });
  fireEvent.touchStart(title, { touches: [{ clientX: 100, clientY: 100 }] });
  fireEvent.touchMove(title, { touches: [{ clientX: 100, clientY: 300 }] });
  fireEvent.touchEnd(title);
}

describe("Weather", () => {
  it("shows now, every tip, 24 hours and 7 days of the home city", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": forecast });
    renderWeather();
    expect(screen.getByRole("heading", { name: "Погода", level: 1 })).toBeInTheDocument();
    await screen.findByRole("heading", { name: "Москва" });
    const now = cardOf("Москва");
    expect(within(now).getByText("+10°")).toBeInTheDocument();
    expect(within(now).getByText("Малооблачно")).toBeInTheDocument();
    expect(within(now).getByText("Ощущается как +7°")).toBeInTheDocument();
    expect(within(now).getByText("Ветер 3 м/с, порывы до 6 м/с")).toBeInTheDocument();
    expect(within(now).getByText("Влажность 71 %")).toBeInTheDocument();
    expect(within(now).getByText("🚲 Сегодня хороший день для велосипеда")).toBeInTheDocument();
    // One city: no row of cities.
    expect(screen.queryByRole("group", { name: "Города" })).not.toBeInTheDocument();
    expect(screen.getByText("🌅 06:40 · 🌇 18:40")).toBeInTheDocument();
  });

  it("lays the next 24 hours out in a strip that reads out each hour", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": forecast });
    renderWeather();
    const strip = await screen.findByRole("region", { name: "Прогноз на 24 часа" });
    expect(strip).toHaveAttribute("tabindex", "0"); // a keyboard scrolls it too
    expect(within(cardOf("24 часа")).getByRole("region")).toBe(strip);
    const cells = within(strip).getAllByRole("listitem");
    expect(cells).toHaveLength(24);
    expect(cells[0]).toHaveAccessibleName("Сейчас, малооблачно, +10°");
    expect(cells[0]).toHaveTextContent("Сейчас");
    expect(cells[1]).toHaveAccessibleName("16:00, малооблачно, +13°");
    // The chance from 20 %: rain is likely at 21:00 only.
    const rain = within(strip).getByRole("listitem", { name: `21:00, малооблачно, +9°, осадки 40${NBSP}%` });
    expect(rain).toHaveTextContent("💧 40 %");
    expect(cells[1]).not.toHaveTextContent("💧");
    expect(within(strip).getAllByText(/💧/)).toHaveLength(1);
    // The icons and the drop are read out in the cell's own words.
    expect(within(rain).getByText("🌙")).toHaveAttribute("aria-hidden", "true");
    expect(within(rain).getByText("💧 40 %")).toHaveAttribute("aria-hidden", "true");
    expect(within(strip).getByRole("img", { name: "Температура на сутки: от +6° до +13°" })).toBeInTheDocument();
  });

  it("puts the chance of the hour going on into «Сейчас»", async () => {
    installTelegram();
    const wet = { ...forecast, now: { ...forecast.now, precip_chance: 60 } };
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": wet });
    renderWeather();
    const strip = await screen.findByRole("region", { name: "Прогноз на 24 часа" });
    expect(within(strip).getAllByRole("listitem")[0]).toHaveAccessibleName(
      `Сейчас, малооблачно, +10°, осадки 60${NBSP}%`,
    );
  });

  it("lists 7 days, today and tomorrow by name, each with its range and a chance from 20 %", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": forecast });
    renderWeather();
    await screen.findByRole("heading", { name: "7 дней" });
    const days = within(cardOf("7 дней")).getAllByRole("listitem");
    expect(days.map((day) => day.getAttribute("aria-label"))).toEqual([
      "Сегодня: малооблачно, от +6° до +13°",
      `Завтра: дождь, от +6° до +11°, осадки 80${NBSP}%`,
      "Среда, 30 сентября: пасмурно, от +5° до +10°",
      "Четверг, 1 октября: ясно, от +3° до +12°",
      "Пятница, 2 октября: малооблачно, от +5° до +14°",
      `Суббота, 3 октября: морось, от +7° до +12°, осадки 20${NBSP}%`,
      "Воскресенье, 4 октября: пасмурно, от +6° до +11°",
    ]);
    expect(days[0]).toHaveTextContent(/^Сегодня/);
    expect(days[2]).toHaveTextContent(/^ср, 30 сент\./);
    expect(within(days[1] as HTMLElement).getByText("💧 80 %")).toBeInTheDocument();
    expect(days[2]).not.toHaveTextContent("💧"); // 10 %
    expect(days[4]).not.toHaveTextContent("💧"); // no chance at all
    expect(within(days[1] as HTMLElement).getByText("+6°")).toBeInTheDocument();
    expect(within(days[1] as HTMLElement).getByText("+11°")).toBeInTheDocument();
  });

  it("ends with the sun, naming no source of the data", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": forecast });
    renderWeather();
    const sun = await screen.findByText("🌅 06:40 · 🌇 18:40");
    expect(sun.nextElementSibling).toBeNull();
    // Open-Meteo, GeoNames and the licence are named in «Ещё» → «Данные».
    expect(screen.queryByText(/open-meteo/)).not.toBeInTheDocument();
  });

  it("names a polar night or day instead of the sunrise and the sunset", async () => {
    installTelegram();
    mockApi({
      "GET /me": me, "GET /me/cities": [], "GET /weather": { ...forecast, sunrise: null, sunset: null, polar: "night" },
    });
    const { unmount } = renderWeather();
    expect(await screen.findByText("🌑 Полярная ночь")).toBeInTheDocument();
    expect(screen.queryByText(/🌅/)).not.toBeInTheDocument();
    unmount();
    mockApi({
      "GET /me": me, "GET /me/cities": [], "GET /weather": { ...forecast, sunrise: null, sunset: null, polar: "day" },
    });
    renderWeather();
    expect(await screen.findByText("☀️ Полярный день")).toBeInTheDocument();
  });

  it("names the gusts only when they blow harder than the wind, and leaves out what is unknown", async () => {
    installTelegram();
    const calm: Forecast = {
      ...forecast,
      now: { ...forecast.now, gusts: 3.2, feels_like: null, humidity: null },
      tips: [],
      hours: [],
      days: [],
    };
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": calm });
    renderWeather();
    await screen.findByRole("heading", { name: "Москва" });
    const now = cardOf("Москва");
    expect(within(now).getByText("Ветер 3 м/с")).toBeInTheDocument();
    expect(within(now).queryByText(/Ощущается/)).not.toBeInTheDocument();
    expect(within(now).queryByText(/Влажность/)).not.toBeInTheDocument();
    // Now alone in the strip, with no curve through one point, and no week without days.
    const strip = screen.getByRole("region", { name: "Прогноз на 24 часа" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(1);
    expect(within(strip).queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "7 дней" })).not.toBeInTheDocument();
  });

  it("speaks English", async () => {
    installTelegram();
    mockApi({ "GET /me": { ...me, language: "en" }, "GET /me/cities": [], "GET /weather": forecast });
    renderWeather("/weather", "en");
    expect(screen.getByRole("heading", { name: "Weather", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Feels like +7°")).toBeInTheDocument();
    expect(screen.getByText("Wind 3 m/s, gusts up to 6 m/s")).toBeInTheDocument();
    expect(screen.getByText("Humidity 71%")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "24-hour forecast" })).toBeInTheDocument();
    const days = within(cardOf("7 days")).getAllByRole("listitem");
    expect(days[0]).toHaveTextContent(/^Today/);
    expect(days[1]).toHaveTextContent(/^Tomorrow/);
    expect(days[2]).toHaveTextContent(/^Wed, Sep 30/);
    expect(days[2]).toHaveAccessibleName("Wednesday, September 30: пасмурно, +5° to +10°");
  });
});

describe("Weather in the extra cities", () => {
  it("switches the city with a chip, in place of the last one", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me, "GET /me/cities": [tula], "GET /weather": forecast, "GET /weather?city=3": TULA,
    });
    const { history } = renderWeather();
    const chips = await screen.findByRole("group", { name: "Города" });
    const home = within(chips).getByRole("button", { name: "🏠 Москва" });
    const other = within(chips).getByRole("button", { name: "Тула" });
    await screen.findByRole("heading", { name: "Москва" });
    expect(home).toHaveAttribute("aria-pressed", "true");
    expect(other).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(other);
    expect(await screen.findByRole("heading", { name: "Тула" })).toBeInTheDocument();
    expect(within(cardOf("Тула")).getByText("+7°")).toBeInTheDocument();
    expect(other).toHaveAttribute("aria-pressed", "true");
    expect(home).toHaveAttribute("aria-pressed", "false");
    expect(history).toEqual(["/weather/3"]); // the back button still leads to «Сегодня»
    expect(calls.map((call) => call.path)).toContain("/weather?city=3");
    fireEvent.click(home);
    expect(await screen.findByRole("heading", { name: "Москва" })).toBeInTheDocument();
    expect(history).toEqual(["/weather"]);
  });

  it("opens an extra city by its address", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [tula], "GET /weather?city=3": TULA });
    renderWeather("/weather/3");
    expect(await screen.findByRole("heading", { name: "Тула" })).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Города" })).getByRole("button", { name: "Тула" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("scrolls the row, and only the row, to the pressed chip when the screen opens and when the city changes", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [tula], "GET /weather": forecast, "GET /weather?city=3": TULA });
    // jsdom lays nothing out: the row stands at 12-308 px, and each chip where this stub puts it along
    // the row, moved by the row's own scroll. The font comes after the chips and widens the Тула chip.
    let fontsIn = false;
    const box = (left: number, right: number) =>
      ({ left, right, top: 0, bottom: 44, width: right - left, height: 44, x: left, y: 0, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      if (this.classList.contains("city-chips")) return box(12, 308);
      const row = this.closest(".city-chips");
      if (row === null) return box(0, 0);
      const other = this.textContent === "Тула";
      const left = 12 + (other ? 330 : 4) - row.scrollLeft;
      return box(left, left + (other ? (fontsIn ? 70 : 67) : 107));
    });
    // Neither may move the page: scrollIntoView would. jsdom has no document.fonts either.
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, writable: true, value: scrollIntoView });
    Object.defineProperty(document, "fonts", {
      configurable: true,
      get: () => ({ ready: Promise.resolve().then(() => (fontsIn = true)) }),
    });
    try {
      renderWeather("/weather/3");
      const chips = await screen.findByRole("group", { name: "Города" });
      // The Тула chip at 342-409, past the row's right edge less 4 px (304): 105 px. Once the font is in
      // it ends at 307 instead: 3 px more.
      await waitFor(() => expect(chips.scrollLeft).toBe(108));
      fireEvent.click(within(chips).getByRole("button", { name: /Москва/ }));
      // The home chip, now at 16 - 108 = -92 px: back to 4 px inside the row's left edge.
      await waitFor(() => expect(chips.scrollLeft).toBe(0));
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      Reflect.deleteProperty(Element.prototype, "scrollIntoView");
      Reflect.deleteProperty(document, "fonts");
    }
  });

  it("goes to the home city when the city is gone, and asks for the list again", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me, "GET /me/cities": [tula], "GET /weather": forecast, "GET /weather?city=3": GONE,
    });
    const { history } = renderWeather("/weather/3");
    expect(await screen.findByText("Этого города уже нет в списке")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Москва" })).toBeInTheDocument();
    expect(history).toEqual(["/weather"]);
    expect(calls.filter((call) => call.path === "/weather?city=3")).toHaveLength(1); // a 404 is not tried again
    await waitFor(() => expect(calls.filter((call) => call.path === "/me/cities")).toHaveLength(2));
    expect(screen.getAllByText("Этого города уже нет в списке")).toHaveLength(1);
  });

  it("takes an address that names no city for a city that is gone", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": forecast });
    const { history } = renderWeather("/weather/tula");
    expect(await screen.findByText("Этого города уже нет в списке")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Москва" })).toBeInTheDocument();
    expect(history).toEqual(["/weather"]);
  });
});

describe("Weather when Open-Meteo fails", () => {
  // The app tries a 5xx twice more, a second and two apart, before it gives up.
  const settle = () => act(() => vi.advanceTimersByTimeAsync(5_000));

  it("says the weather is unavailable, and tries again on «Повторить»", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    installTelegram();
    let reply: unknown = UNAVAILABLE;
    const { calls } = mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": () => reply });
    renderWeather();
    await settle();
    expect(screen.getByText("Погода временно недоступна")).toBeInTheDocument();
    expect(calls.filter((call) => call.path === "/weather")).toHaveLength(3);
    reply = { body: forecast };
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByRole("heading", { name: "Москва" })).toBeInTheDocument();
  });

  it("keeps the forecast shown when a refresh fails, and shows a fresh one after a refresh that works", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    installTelegram();
    let reply: unknown = { body: forecast };
    const { calls } = mockApi({ "GET /me": me, "GET /me/cities": [], "GET /weather": () => reply });
    renderWeather();
    expect(await screen.findByRole("heading", { name: "Москва" })).toBeInTheDocument();
    reply = UNAVAILABLE;
    pullDown();
    await settle();
    expect(calls.filter((call) => call.path === "/weather")).toHaveLength(4);
    expect(screen.queryByText("Погода временно недоступна")).not.toBeInTheDocument();
    expect(within(cardOf("Москва")).getByText("+10°")).toBeInTheDocument();
    reply = { body: { ...forecast, now: { ...forecast.now, temperature: 12.4 } } };
    pullDown();
    await settle();
    expect(within(cardOf("Москва")).getByText("+12°")).toBeInTheDocument();
  });
});
