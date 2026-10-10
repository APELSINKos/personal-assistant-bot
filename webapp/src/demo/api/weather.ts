/**
 * The weather (routers/weather.py, services/weather.py): a city's forecast on its own clock, and its
 * week as a picture to share or to send. The weather is made up but holds together: each place has
 * its seasons (a mean that follows the day of the year), each day a shift drawn from its date, bands
 * of rain — snow at 0 °C and below — by the hours of the place's day, and the sun's times by the
 * formula of the sky.
 */
import type { ClassesWeather, Forecast, ForecastDay, ForecastHour, SharedCard, Weather } from "../../api/types";
import { addDaysIso, daysBetween } from "../../lib/format";
import type { Place, Visit } from "./data";
import { json, noContent, notFound, route, writeForbidden, type Route } from "./http";
import { preparedId } from "./prepared";
import { chance } from "./random";
import { clockOf, dayOf, HOUR, localClock, MINUTE, momentOf, wall, type Wall } from "./time";
import { ID_MAX, queryInt } from "./validate";
import { TEXTS, type WeatherWord } from "./words";

type Rain = "rain" | "showers" | "drizzle";

/** The weather of a city's days: bands of rain [from hour, to hour, peak %, kind], counted from its today's midnight. */
interface Pattern {
  bands: readonly (readonly [number, number, number, Rain])[];
  /** The chance of rain outside the bands. */
  base: number;
  fog?: readonly (readonly [number, number])[];
  /** A dry place's sky is clear, not partly cloudy. */
  clear?: boolean;
  wind: number;
  gusts: number;
  humidity: number;
}

const PATTERNS: readonly Pattern[] = [
  // The home city: drizzle in the morning, rain from 17:00 into the night, showers on the third day,
  // a wet fifth day.
  {
    bands: [[7, 10, 45, "drizzle"], [17, 26, 90, "rain"], [31, 35, 60, "drizzle"], [82, 92, 70, "showers"], [120, 143, 100, "rain"]],
    base: 5, fog: [[53, 56]], wind: 10.2, gusts: 17.8, humidity: 81,
  },
  // The extra cities, by their place in the list.
  { bands: [[13, 22, 65, "showers"], [48, 71, 40, "rain"]], base: 10, wind: 4.1, gusts: 7.9, humidity: 74 },
  { bands: [[5, 14, 80, "drizzle"], [24, 47, 50, "drizzle"], [96, 130, 95, "rain"]], base: 25, wind: 6.3, gusts: 11, humidity: 92 },
  { bands: [[111, 114, 25, "showers"]], base: 0, clear: true, wind: 2.1, gusts: 4.5, humidity: 38 },
  { bands: [[0, 23, 95, "rain"], [30, 40, 60, "rain"]], base: 40, wind: 8, gusts: 14.2, humidity: 88 },
];
/** A little unevenness of the chances from hour to hour. */
const WOBBLE = [0, 3, -2, 5, -4, 2, -1, 4];

/** The seasons of the places of the demo's story: [latitude, longitude, the year's mean, its swing, a day's swing]. */
const CLIMATES: readonly (readonly [number, number, number, number, number])[] = [
  [55.75, 37.62, 5.8, 13, 3.5], // Москва
  [54.2, 37.62, 5.5, 13.5, 4], // Тула
  [53.04, 158.65, 2.5, 8, 3], // Петропавловск-Камчатский
  [40.18, 44.51, 12.5, 15, 7], // Ереван
];

/** weather.py's codes: the icon and the words of a WMO code, the moon instead of a clear sky at night. */
const CODES: readonly (readonly [number, number, string, WeatherWord])[] = [
  [0, 0, "☀️", "clear"], [1, 2, "🌤", "partly"], [3, 3, "☁️", "cloudy"], [45, 48, "🌫", "fog"],
  [51, 57, "🌦", "drizzle"], [61, 67, "🌧", "rain"], [71, 77, "🌨", "snow"], [80, 82, "🌧", "showers"],
  [85, 86, "🌨", "snowfall"], [95, 99, "⛈", "storm"],
];

const round1 = (value: number) => Math.round(value * 10) / 10;
const pad = (value: number) => String(value).padStart(2, "0");

function describe(code: number, lang: Visit["language"], isDay = true): [string, string] {
  const found = CODES.find(([first, last]) => first <= code && code <= last);
  if (!found) return ["🌡", TEXTS[lang].weather.unknown];
  return [!isDay && code <= 2 ? "🌙" : found[2], TEXTS[lang].weather[found[3]]];
}

/** A place's mean temperature on a day of the year: m − a·cos(2π(day − 15)/365), the south the other way round. */
function seasonal(place: Place, day: string): { mean: number; swing: number } {
  const known = CLIMATES.find(([lat, lon]) => Math.abs(lat - place.lat) < 0.5 && Math.abs(lon - place.lon) < 0.5);
  const latitude = Math.abs(place.lat);
  const [mean, amplitude, swing] = known
    ? [known[2], known[3], known[4]]
    : [26 - 0.36 * latitude, Math.min(15, Math.max(3, 0.3 * latitude - 3)), 4];
  const dayOfYear = daysBetween(`${day.slice(0, 4)}-01-01`, day) + 1;
  const season = Math.cos((2 * Math.PI * (dayOfYear - 15)) / 365) * (place.lat < 0 ? -1 : 1);
  // A day warmer or colder than the season, drawn from its date: the same on every visit.
  const shift = (chance(day, place.lat.toFixed(2), place.lon.toFixed(2), "weather") - 0.5) * 5;
  return { mean: mean - amplitude * season + shift, swing };
}

interface Sun {
  polar: "night" | "day" | null;
  /** Hours from the local midnight. */
  rise: number;
  set: number;
  riseAt: number;
  setAt: number;
}

/** Sunrise and sunset of a local day (NOAA's approximation), or a polar night or day. */
function sun(place: Place, day: string): Sun {
  const [year = 2026, month = 1, date = 1] = day.split("-").map(Number);
  const gamma = ((2 * Math.PI) / 365) * daysBetween(`${year}-01-01`, day);
  const eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
    - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma));
  const decl = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma) - 0.006758 * Math.cos(2 * gamma)
    + 0.000907 * Math.sin(2 * gamma) - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);
  const rad = Math.PI / 180;
  const cos = (Math.cos(90.833 * rad) - Math.sin(place.lat * rad) * Math.sin(decl))
    / (Math.cos(place.lat * rad) * Math.cos(decl));
  if (cos > 1) return { polar: "night", rise: 0, set: 0, riseAt: 0, setAt: 0 };
  if (cos < -1) return { polar: "day", rise: 0, set: 0, riseAt: 0, setAt: 0 };
  const noon = Date.UTC(year, month - 1, date) + (720 - 4 * place.lon - eqtime) * MINUTE;
  const half = 4 * (Math.acos(cos) / rad) * MINUTE;
  const midnight = momentOf(place.timezone, day);
  return {
    polar: null, rise: (noon - half - midnight) / HOUR, set: (noon + half - midnight) / HOUR,
    riseAt: noon - half, setAt: noon + half,
  };
}

/** A place's weather around now. Its hours count from the midnight of the place's today: 27 is tomorrow's 03:00. */
export interface Model {
  place: Place;
  pattern: Pattern;
  local: Wall;
  /** The place's today and the seven days after it. */
  days: string[];
  suns: Sun[];
  /** Now, in hours from the midnight of the place's today. */
  at: number;
  temperature(hour: number): number;
  chance(hour: number): number;
  /** An hour's label tells of the hour before it, as Open-Meteo's precipitation_probability does. */
  labelChance(label: number): number;
  code(hour: number): number;
  isDay(hour: number): boolean;
}

/** The weather of a place: `patternIndex` 0 is the home city's, 1 to 4 the extra cities'. */
export function model(visit: Visit, place: Place, patternIndex: number): Model {
  const pattern = PATTERNS[patternIndex] ?? (PATTERNS[0] as Pattern);
  const local = wall(place.timezone, visit.now());
  const first = dayOf(local);
  const days = Array.from({ length: 8 }, (_, offset) => addDaysIso(first, offset));
  const seasons = days.map((day) => seasonal(place, day));
  const suns = days.map((day) => sun(place, day));
  const swing = seasons[0]?.swing ?? 4;
  const temperature = (hour: number) => {
    const middle = Math.min(6, Math.max(0, hour / 24 - 0.5));
    const index = Math.min(5, Math.floor(middle));
    const from = seasons[index]?.mean ?? 0;
    const to = seasons[index + 1]?.mean ?? from;
    const clock = hour - 24 * Math.floor(hour / 24);
    const curve = clock < 6
      ? Math.cos((Math.PI * (clock + 9)) / 15)
      : clock <= 15 ? -Math.cos((Math.PI * (clock - 6)) / 9) : Math.cos((Math.PI * (clock - 15)) / 15);
    return round1(from + (to - from) * (middle - index) + swing * curve);
  };
  const rainChance = (hour: number) => {
    let value = pattern.base;
    for (const [from, to, peak] of pattern.bands) {
      if (hour >= from && hour <= to) {
        value = Math.max(value, Math.round(peak * Math.min(1, (Math.min(hour - from, to - hour) + 1) / 3)));
      }
    }
    const wobble = value > 0 && value < 100 ? (WOBBLE[((Math.floor(hour) % 8) + 8) % 8] ?? 0) : 0;
    return Math.max(0, Math.min(100, value + wobble));
  };
  const code = (hour: number) => {
    const value = rainChance(hour);
    const band = pattern.bands.find(([from, to]) => hour >= from && hour <= to);
    const kind: Rain = band ? band[3] : "rain";
    const cold = temperature(hour) <= 0;
    if (value >= 75) return cold ? 73 : { rain: 63, showers: 81, drizzle: 55 }[kind];
    if (value >= 55) return cold ? 71 : { rain: 61, showers: 80, drizzle: 53 }[kind];
    if (pattern.fog?.some(([from, to]) => hour >= from && hour <= to)) return 45;
    if (value >= 30) return 3;
    if (value >= 15) return 2;
    return pattern.clear ? 0 : 1;
  };
  const isDay = (hour: number) => {
    const today = suns[Math.min(7, Math.max(0, Math.floor(hour / 24)))];
    if (!today) return true;
    if (today.polar) return today.polar === "day";
    const clock = hour - 24 * Math.floor(hour / 24);
    return clock >= today.rise && clock < today.set;
  };
  return {
    place, pattern, local, days, suns,
    at: local.hour + local.minute / 60 + local.second / 3600,
    temperature, chance: rainChance, labelChance: (label) => rainChance(label - 0.5), code, isDay,
  };
}

const nowTemperature = (w: Model) => w.temperature(w.at);

function feelsLike(w: Model): number {
  const value = nowTemperature(w);
  return round1(value < 10 ? value - 1 - 0.33 * w.pattern.wind : value + (w.pattern.humidity - 60) / 20);
}

/** weather.py's build_tips: rain now, soon (within two hours) or later today; the evening; wind, frost, heat. */
function tips(w: Model, lang: Visit["language"]): string[] {
  const words = TEXTS[lang].tips;
  const snow = nowTemperature(w) <= 0;
  const found: string[] = [];
  let soon = false;
  let later = false;
  if (w.chance(w.at) >= 80) {
    found.push(words.now(snow));
    soon = true;
  } else {
    for (let quarter = Math.floor(w.at * 4) + 1; quarter <= Math.floor(w.at * 4) + 8; quarter += 1) {
      const minutes = Math.round((quarter / 4 - w.at) * 60);
      if (minutes > 0 && minutes <= 120 && w.chance(quarter / 4) >= 80) {
        found.push(words.soon(snow, minutes));
        soon = true;
        break;
      }
    }
  }
  if (!soon) {
    for (let label = Math.floor(w.at) + 1; label < 24; label += 1) {
      if (label - 1 > w.at && w.labelChance(label) >= 60) {
        found.push(words.later(snow, `${pad(label - 1)}:00`));
        later = true;
        break;
      }
    }
  }
  const evening = w.temperature(18) - w.temperature(8);
  if (evening >= 5) found.push(words.warmer);
  else if (evening <= -5) found.push(words.colder);
  const feels = feelsLike(w);
  if (w.pattern.wind >= 10) found.push(words.wind);
  if (feels <= -15) found.push(words.frost);
  if (feels >= 30) found.push(words.heat);
  const warmest = Math.max(...Array.from({ length: 24 }, (_, hour) => w.temperature(hour)));
  if (!(soon || later) && warmest >= 12 && warmest <= 28 && w.pattern.wind < 7) found.push(words.bike);
  return found.length ? found : [words.calm];
}

/** A day of the forecast: the heaviest weather of its hours, its lowest and highest, its highest chance. */
export function dayOut(w: Model, index: number, lang: Visit["language"]): ForecastDay {
  const labels = Array.from({ length: 24 }, (_, hour) => 24 * index + hour);
  const temperatures = labels.map(w.temperature);
  const [emoji, description] = describe(Math.max(...labels.map(w.code)), lang);
  return {
    date: w.days[index] ?? "", emoji, description, tmin: Math.min(...temperatures), tmax: Math.max(...temperatures),
    precip_chance: Math.max(...labels.map(w.labelChance)),
  };
}

function forecastOut(w: Model, city: Forecast["city"], lang: Visit["language"]): Forecast {
  const [emoji, description] = describe(w.code(w.at), lang, w.isDay(w.at));
  const hours = Array.from({ length: 23 }, (_, index): ForecastHour => {
    const hour = Math.floor(w.at) + 1 + index;
    const [icon, words] = describe(w.code(hour), lang, w.isDay(hour));
    return {
      time: `${pad(hour % 24)}:00`, emoji: icon, description: words, temperature: w.temperature(hour),
      precip_chance: w.labelChance(hour),
    };
  });
  const first = w.suns[0];
  const clock = (moment: number) => localClock(w.place.timezone, moment);
  return {
    city,
    now: {
      temperature: nowTemperature(w), feels_like: feelsLike(w), wind: w.pattern.wind, gusts: w.pattern.gusts,
      humidity: w.pattern.humidity, is_day: w.isDay(w.at), emoji, description,
      precip_chance: w.labelChance(Math.ceil(w.at - 1e-9)),
    },
    tips: tips(w, lang),
    hours,
    days: Array.from({ length: 7 }, (_, index) => dayOut(w, index, lang)),
    sunrise: !first || first.polar ? null : clock(first.riseAt),
    sunset: !first || first.polar ? null : clock(first.setAt),
    polar: first?.polar ?? null,
  };
}

/** The home city's weather around now. */
export const homeModel = (visit: Visit): Model => model(visit, visit.data.profile.home, 0);

/** «Сегодня»'s weather: the home city now, as the bot's weather card shows it. */
export function weatherOut(visit: Visit, w: Model): Weather {
  const lang = visit.lang();
  const code = w.code(w.at);
  const [emoji, description] = describe(code, lang, w.isDay(w.at));
  const day = dayOut(w, 0, lang);
  return {
    city: visit.data.profile.home.name, temperature: nowTemperature(w), feels_like: feelsLike(w), wind: w.pattern.wind,
    code, emoji, description, tmin: day.tmin, tmax: day.tmax, tips: tips(w, lang),
  };
}

/**
 * The weather of the way to today's first class and back after the last one (weather.classes_weather):
 * the hours on the city's clock, the times on the user's; a chance under 30 % is not worth saying.
 */
export function classesWeather(visit: Visit, w: Model, lessons: { start: number; end: number }[]): ClassesWeather | null {
  if (!lessons.length) return null;
  const start = Math.min(...lessons.map((lesson) => lesson.start));
  const end = Math.max(...lessons.map((lesson) => lesson.end));
  const midnight = momentOf(w.place.timezone, w.days[0] ?? "");
  const at = (moment: number) => (moment - midnight) / HOUR;
  const worth = (value: number) => (value >= 30 ? value : null);
  return {
    start: clockOf(wall(visit.zone(), start)), start_temp: w.temperature(Math.floor(at(start))),
    start_chance: worth(w.labelChance(Math.ceil(at(start)))),
    end: clockOf(wall(visit.zone(), end)), end_temp: w.temperature(Math.floor(at(end))),
    end_chance: worth(w.labelChance(Math.ceil(at(end)))),
  };
}

/** The city a request names: the home one for 0, else one of the extra cities — 404 for one not there. */
function cityOf(visit: Visit, query: URLSearchParams): { shown: Forecast["city"]; w: Model } {
  const id = queryInt(query, "city", { ge: 0, le: ID_MAX }) ?? 0;
  if (!id) return { shown: { id: 0, name: visit.data.profile.home.name, home: true }, w: homeModel(visit) };
  const index = visit.data.cities.findIndex((city) => city.id === id);
  const city = visit.data.cities[index];
  if (!city) throw notFound("city");
  return { shown: { id, name: city.name, home: false }, w: model(visit, city, 1 + (index % 4)) };
}

export const WEATHER: Route[] = [
  route("GET", "/weather", (visit, { query }) => {
    const { shown, w } = cityOf(visit, query);
    return json<Forecast>(forecastOut(w, shown, visit.lang()));
  }),
  // Nothing is drawn: the host page's chat picker shows the README's sample of the week.
  route("POST", "/weather/share", (visit, { query }) => {
    const { shown } = cityOf(visit, query);
    visit.data.shared += 1;
    return json<SharedCard>({ prepared_id: preparedId("forecast", shown.id, visit.data.shared) });
  }),
  route("POST", "/weather/card", (visit, { query }) => {
    cityOf(visit, query);
    if (!visit.data.profile.can_write) throw writeForbidden();
    return noContent();
  }),
];
