/**
 * The demo's API in the host page (spec §5): it answers the app's requests from memory, as the
 * routers of src/assistant/api answer them on the server. For now a stand-in that knows the visitor
 * and the day, so that «Сегодня» opens; any other request gets the server's 404 for an unknown path.
 */
import type { Me, Today } from "../../api/types";
import type { Lang } from "../../i18n";
import type { ApiReply, ApiRequest } from "../bridge/contract";
import { moscowDay, moscowHour } from "./clock";
import { WORDS } from "./words";

export interface ApiOptions {
  language: Lang;
  /** The demo's clock: the real one, or the one `?at=` moved. */
  now: () => number;
}

export type DemoApi = (request: ApiRequest) => ApiReply;

function ok(body: unknown): ApiReply {
  return { status: 200, body, headers: { "Content-Type": "application/json" } };
}

/** As errors.py writes a problem: application/problem+json with the API's own code. */
function problem(status: number, code: string, title: string): ApiReply {
  return {
    status,
    body: { type: "about:blank", title, status, code },
    headers: { "Content-Type": "application/problem+json" },
  };
}

/** As core/services/digest.py splits the day. */
function partOfDay(hour: number): Today["part_of_day"] {
  if (hour >= 5 && hour <= 11) return "morning";
  if (hour >= 12 && hour <= 16) return "day";
  if (hour >= 17 && hour <= 22) return "evening";
  return "night";
}

export function createApi({ language, now }: ApiOptions): DemoApi {
  const words = WORDS[language];
  // routers/me.py: the profile.
  const me: Me = {
    id: 1,
    first_name: words.name,
    language,
    language_setting: "auto",
    city: { name: words.home, lat: 55.7558, lon: 37.6173, timezone: "Europe/Moscow" },
    morning: { enabled: true, time: "08:00" },
    can_write: true,
    currency: "RUB",
    money_budget: 3_000_000,
  };
  // routers/today.py: the day, with nothing in it yet.
  const today = (): Today => {
    const moment = now();
    return {
      date: moscowDay(moment),
      part_of_day: partOfDay(moscowHour(moment)),
      weather: null,
      reminders_today: [],
      habits: { done: 0, total: 0, items: [] },
      notes_count: 0,
      rates: null,
      best_streak: null,
      has_schedule: false,
      lessons: [],
      week_label: null,
      money: null,
      tomorrow: null,
      classes_weather: null,
      pinned_notes: [],
    };
  };
  return (request) => {
    if (request.method === "GET" && request.path === "/me") return ok(me);
    if (request.method === "GET" && request.path === "/today") return ok(today());
    return problem(404, "not_found", "Not Found");
  };
}
