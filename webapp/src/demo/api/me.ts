/**
 * The profile (routers/me.py with services/users.py and services/cities.py; routers/health.py): the
 * user and their settings, the extra cities of the weather and the search that finds them.
 */
import { version } from "../../../package.json";
import type { City, Health, Me, WeatherCity } from "../../api/types";
import type { Lang } from "../../i18n";
import { codePoints } from "../../lib/format";
import { CURRENCY_CODES } from "../../lib/money";
import { cleanItem } from "../../lib/notes";
import type { Visit } from "./data";
import { created, invalidInput, json, limitReached, noContent, notFound, route, type Route } from "./http";
import { searchPlaces } from "./places";
import { parseClock, validZone } from "./time";
import { check, ID_MAX, itemId, queryText, type Fields } from "./validate";

/** LIMITS.cities: the extra cities besides the home one. */
const CITIES = 4;
/** cities.NAME_LENGTH: a name, a region or a country as kept. */
const NAME_LENGTH = 100;
/** cities.NEAR: two points within this many degrees on each axis are one place. */
const NEAR = 0.01;

const LAT = { type: "float", required: true, ge: -90, le: 90 } as const;
const LON = { type: "float", required: true, ge: -180, le: 180 } as const;
const ZONE = { type: "str", required: true, min: 1, max: 64 } as const;
const GEO_ID = { type: "int", nullable: true, ge: 1, le: ID_MAX } as const;

const ME_PATCH: Fields = {
  language: { type: "str", nullable: true, choices: ["auto", "ru", "en"] },
  morning_enabled: { type: "bool", nullable: true },
  morning_time: { type: "str", nullable: true, max: 5 },
  currency: { type: "str", nullable: true, max: 3 },
};
const CITY_IN: Fields = {
  name: { type: "str", required: true, min: 1, max: NAME_LENGTH }, lat: LAT, lon: LON, timezone: ZONE, geo_id: GEO_ID,
};
const WEATHER_CITY_IN: Fields = {
  name: { type: "str", required: true, min: 1, max: NAME_LENGTH },
  admin: { type: "str", nullable: true, max: NAME_LENGTH },
  country: { type: "str", nullable: true, max: NAME_LENGTH },
  lat: LAT, lon: LON, timezone: ZONE, geo_id: GEO_ID,
};

interface MePatchIn {
  language?: "auto" | Lang | null;
  morning_enabled?: boolean | null;
  morning_time?: string | null;
  currency?: string | null;
}

interface CityIn {
  name: string;
  admin?: string | null;
  country?: string | null;
  lat: number;
  lon: number;
  timezone: string;
  geo_id?: number | null;
}

export function meOut(visit: Visit): Me {
  const { profile } = visit.data;
  const { name, lat, lon, timezone } = profile.home;
  return {
    id: 1,
    first_name: profile.first_name,
    language: visit.lang(),
    language_setting: profile.language,
    city: { name, admin: null, country: null, lat, lon, timezone },
    morning: { ...profile.morning },
    can_write: profile.can_write,
    currency: profile.currency,
    money_budget: profile.budget,
  };
}

/** cities.same_place: one place for the weather, across the 180th meridian too. */
function samePlace(lat1: number, lon1: number, lat2: number, lon2: number): boolean {
  const east = Math.abs(lon1 - lon2) % 360;
  return Math.abs(lat1 - lat2) <= NEAR + 1e-9 && Math.min(east, 360 - east) <= NEAR + 1e-9;
}

const invalidCity = () => invalidInput({ field: "city", reason: "invalid" });

/** cities._columns: what is kept of a place the app sends back, or invalid. */
function cityColumns(city: CityIn): Omit<WeatherCity, "id"> {
  const name = cleanItem(city.name);
  const admin = cleanItem(city.admin ?? "");
  const country = cleanItem(city.country ?? "");
  const longest = Math.max(codePoints(name), codePoints(admin), codePoints(country));
  if (!name || longest > NAME_LENGTH || !validZone(city.timezone)) throw invalidCity();
  return {
    name, admin: admin || null, country: country || null, lat: city.lat, lon: city.lon, timezone: city.timezone,
    geo_id: city.geo_id ?? null,
  };
}

export const ME: Route[] = [
  route("GET", "/health", () => json<Health>({ status: "ok", version, commit: null })),
  route("GET", "/me", (visit) => json<Me>(meOut(visit))),
  route("PATCH", "/me", (visit, { body }) => {
    check(body, ME_PATCH);
    const patch = body as MePatchIn;
    const { profile } = visit.data;
    // Every change or none: the server commits them together.
    const time = patch.morning_time == null ? null : parseClock(patch.morning_time);
    if (patch.morning_time != null && time === null) throw invalidInput({ field: "time", reason: "format" });
    if (patch.currency != null && !CURRENCY_CODES.includes(patch.currency)) {
      throw invalidInput({ field: "currency", reason: "unsupported" });
    }
    if (patch.language != null) profile.language = patch.language;
    if (time !== null) profile.morning.time = time;
    if (patch.morning_enabled != null) profile.morning.enabled = patch.morning_enabled;
    if (patch.currency != null) profile.currency = patch.currency;
    return json<Me>(meOut(visit));
  }),
  route("PUT", "/me/city", (visit, { body }) => {
    check(body, CITY_IN);
    const city = body as CityIn;
    const name = cleanItem(city.name);
    if (!name || codePoints(name) > NAME_LENGTH || !validZone(city.timezone)) throw invalidCity();
    // The new home leaves the extra cities: by the found place's GeoNames id, or as the same place.
    visit.data.cities = visit.data.cities.filter((other) =>
      !((city.geo_id != null && other.geo_id === city.geo_id) || samePlace(city.lat, city.lon, other.lat, other.lon)));
    visit.data.profile.home = { name, lat: city.lat, lon: city.lon, timezone: city.timezone };
    return json<Me>(meOut(visit));
  }),
  route("POST", "/me/write-access", (visit) => {
    visit.data.profile.can_write = true;
    return json<Me>(meOut(visit));
  }),
  route("GET", "/me/cities", (visit) => json<WeatherCity[]>(visit.data.cities)),
  route("POST", "/me/cities", (visit, { body }) => {
    check(body, WEATHER_CITY_IN);
    const columns = cityColumns(body as CityIn);
    const { cities, profile } = visit.data;
    if (cities.length >= CITIES) throw limitReached("city", CITIES);
    const near = (other: { lat: number; lon: number }) => samePlace(columns.lat, columns.lon, other.lat, other.lon);
    const kept = cities.some((other) => (columns.geo_id === null || other.geo_id === null) && near(other))
      || (columns.geo_id !== null && cities.some((other) => other.geo_id === columns.geo_id));
    if (near(profile.home) || kept) throw invalidInput({ field: "city", reason: "duplicate" });
    const added: WeatherCity = { id: visit.data.next.city++, ...columns };
    cities.push(added);
    return created<WeatherCity>(added);
  }),
  route("DELETE", "/me/cities/{city_id}", (visit, { params }) => {
    const id = itemId(params.city_id ?? "", "city_id");
    if (!visit.data.cities.some((city) => city.id === id)) throw notFound("city");
    visit.data.cities = visit.data.cities.filter((city) => city.id !== id);
    return noContent();
  }),
  route("GET", "/cities", (visit, { query }) => {
    const q = queryText(query, "q", { required: true, min: 2, max: 50 }) ?? "";
    return json<City[]>(searchPlaces(q.trim(), visit.lang()));
  }),
];
