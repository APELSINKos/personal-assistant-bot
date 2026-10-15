/**
 * The cities (routers/me.py's search, core/clients/openmeteo.py's geocoding, services/cities.py):
 * a gazetteer of about twenty places named in both languages, as Open-Meteo's search finds them by
 * GeoNames; any other name finds nothing (spec §5.1).
 */
import type { City } from "../../api/types";
import type { Lang } from "../../i18n";

/** The name, the region and the country. */
type Names = readonly [string, string, string];

interface Known {
  geo_id: number;
  ru: Names;
  en: Names;
  lat: number;
  lon: number;
  timezone: string;
}

// The GeoNames id; the names in Russian, then in English; the latitude, the longitude and the zone.
type Row = readonly [number, Names, Names, number, number, string];

const ROWS: readonly Row[] = [
  [524901, ["Москва", "Москва", "Россия"], ["Moscow", "Moscow", "Russia"], 55.75222, 37.61556, "Europe/Moscow"],
  [498817, ["Санкт-Петербург", "Санкт-Петербург", "Россия"], ["Saint Petersburg", "St.-Petersburg", "Russia"], 59.93863, 30.31413, "Europe/Moscow"],
  [551487, ["Казань", "Татарстан", "Россия"], ["Kazan", "Tatarstan", "Russia"], 55.78874, 49.12214, "Europe/Moscow"],
  [1496747, ["Новосибирск", "Новосибирская область", "Россия"], ["Novosibirsk", "Novosibirsk Oblast", "Russia"], 55.0415, 82.9346, "Asia/Novosibirsk"],
  [1486209, ["Екатеринбург", "Свердловская область", "Россия"], ["Yekaterinburg", "Sverdlovsk Oblast", "Russia"], 56.8519, 60.6122, "Asia/Yekaterinburg"],
  [480562, ["Тула", "Тульская область", "Россия"], ["Tula", "Tula Oblast", "Russia"], 54.19609, 37.61822, "Europe/Moscow"],
  [491422, ["Сочи", "Краснодарский край", "Россия"], ["Sochi", "Krasnodar Krai", "Russia"], 43.59917, 39.72569, "Europe/Moscow"],
  [554234, ["Калининград", "Калининградская область", "Россия"], ["Kaliningrad", "Kaliningrad Oblast", "Russia"], 54.70649, 20.51095, "Europe/Kaliningrad"],
  [2013348, ["Владивосток", "Приморский край", "Россия"], ["Vladivostok", "Primorye", "Russia"], 43.10562, 131.87353, "Asia/Vladivostok"],
  [2122104, ["Петропавловск-Камчатский", "Камчатский край", "Россия"], ["Petropavlovsk-Kamchatsky", "Kamchatka Krai", "Russia"], 53.04444, 158.65076, "Asia/Kamchatka"],
  [625144, ["Минск", "Минск", "Беларусь"], ["Minsk", "Minsk City", "Belarus"], 53.9, 27.56667, "Europe/Minsk"],
  [1526384, ["Алматы", "Алматы", "Казахстан"], ["Almaty", "Almaty", "Kazakhstan"], 43.25, 76.91667, "Asia/Almaty"],
  [1526273, ["Астана", "Астана", "Казахстан"], ["Astana", "Astana", "Kazakhstan"], 51.1801, 71.44598, "Asia/Almaty"],
  [616052, ["Ереван", "Ереван", "Армения"], ["Yerevan", "Yerevan", "Armenia"], 40.18111, 44.51361, "Asia/Yerevan"],
  [611717, ["Тбилиси", "Тбилиси", "Грузия"], ["Tbilisi", "Tbilisi", "Georgia"], 41.69411, 44.83368, "Asia/Tbilisi"],
  [1512569, ["Ташкент", "Ташкент", "Узбекистан"], ["Tashkent", "Tashkent", "Uzbekistan"], 41.26465, 69.21627, "Asia/Tashkent"],
  [1528675, ["Бишкек", "Бишкек", "Киргизия"], ["Bishkek", "Bishkek", "Kyrgyzstan"], 42.87, 74.59, "Asia/Bishkek"],
  [2643743, ["Лондон", "Англия", "Великобритания"], ["London", "England", "United Kingdom"], 51.50853, -0.12574, "Europe/London"],
  [2988507, ["Париж", "Иль-де-Франс", "Франция"], ["Paris", "Île-de-France", "France"], 48.85341, 2.3488, "Europe/Paris"],
  [2950159, ["Берлин", "Берлин", "Германия"], ["Berlin", "Land Berlin", "Germany"], 52.52437, 13.41053, "Europe/Berlin"],
];

export const PLACES: readonly Known[] = ROWS.map(([geo_id, ru, en, lat, lon, timezone]) => ({
  geo_id, ru, en, lat, lon, timezone,
}));

/** As Open-Meteo's search compares names: case, «ё» and hyphens aside. */
const fold = (text: string) => text.toLowerCase().replaceAll("ё", "е").replace(/[\s-]+/g, " ").trim();

/** A known place as the search answers with it, named in `lang`. */
export function placeOut(place: Known, lang: Lang): City {
  const [name, admin, country] = place[lang];
  return { name, admin, country, lat: place.lat, lon: place.lon, timezone: place.timezone, geo_id: place.geo_id };
}

/** The place known by its GeoNames id. */
export function knownPlace(geoId: number): Known {
  const found = PLACES.find((place) => place.geo_id === geoId);
  if (!found) throw new Error(`No place ${geoId} in the gazetteer`);
  return found;
}

/**
 * The places whose name, in either language, begins with the query or has a word that does: «пет»
 * finds Санкт-Петербург, «kamch» Petropavlovsk-Kamchatsky. Named in the user's language.
 */
export function searchPlaces(query: string, lang: Lang): City[] {
  const wanted = fold(query.split(",")[0] ?? "");
  if (!wanted) return [];
  const fits = (name: string) => {
    const folded = fold(name);
    return folded.startsWith(wanted) || folded.split(" ").some((word) => word.startsWith(wanted));
  };
  return PLACES.filter((place) => fits(place.ru[0]) || fits(place.en[0]))
    .slice(0, 10)
    .map((place) => placeOut(place, lang));
}
