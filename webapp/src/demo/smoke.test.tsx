// Every screen of the app on the demo (spec §18): the frame's bridges on a test stand, the demo's API
// with its data behind them, and <App/> opened on each of the app's 22 screen routes in both
// languages. No screen may show an error, and each shows a text of its own — so a route the demo
// forgot, or a screen that went somewhere else, is caught here and not by a visitor.
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Lang } from "../i18n";
import { ROUTES } from "../routes";
import { createApi } from "./api";
import { demoFetch } from "./bridge/fetch";
import { installTelegram } from "./bridge/telegram";
import { testHost } from "./bridge/testHost";

/** Wednesday 7 October 2026, 10:30 in Moscow: the moment of the README's pictures. */
const MORNING = Date.UTC(2026, 9, 7, 7, 30);

/** A text of the screen's own, or the value of one of its fields. */
type Known = string | RegExp | { value: string };

/** Each screen route of the app, opened at a place of the demo's data, with what it shows in Russian and in English. */
const SCREENS: [route: string, path: string, ru: Known, en: Known][] = [
  ["/", "/", "Забрать посылку", "Pick up the parcel"],
  ["/weather/:id?", "/weather", "Петропавловск-Камчатский", "Petropavlovsk-Kamchatsky"],
  ["/calendar", "/calendar", "2 пары · 4 напоминания", "2 classes · 4 reminders"],
  ["/calendar/new/:date?", "/calendar/new", "Новое напоминание", "New reminder"],
  ["/calendar/:id", "/calendar/1", { value: "Забрать посылку" }, { value: "Pick up the parcel" }],
  ["/habits", "/habits", /из 3 на этой неделе/, /of 3 this week/],
  ["/habits/new", "/habits/new", "Новая привычка", "New habit"],
  ["/habits/:id", "/habits/1", "Каждый день · с 2 сентября 2025", "Every day · since September 2, 2025"],
  ["/habits/:id/edit", "/habits/1/edit", { value: "Спорт" }, { value: "Sport" }],
  ["/notes", "/notes", "Вернуть Диме 1 500 ₽ до пятницы", "Pay Dima back 1,500 ₽ by Friday"],
  ["/notes/new", "/notes/new", "Новая заметка", "New note"],
  ["/notes/:id", "/notes/1", { value: "Покупки" }, { value: "Shopping" }],
  ["/money", "/money", "подработка", "part-time job"],
  ["/money/new", "/money/new", "Новая запись", "New entry"],
  ["/money/budget", "/money/budget", "Бюджет на месяц", "Monthly budget"],
  ["/money/categories", "/money/categories", "Подарили", "Gifts received"],
  ["/money/categories/new", "/money/categories/new", "Новая категория", "New category"],
  ["/money/categories/:id", "/money/categories/2", { value: "Кафе" }, { value: "Eating out" }],
  ["/money/rates", "/money/rates", "Курсы ЦБ", "Central Bank rates"],
  ["/money/:id/edit", "/money/1/edit", "Удалить запись", "Delete the entry"],
  ["/more", "/more", "Ереван", "Yerevan"],
  ["/more/schedule", "/more/schedule", "Впереди 140 пар", "140 classes ahead"],
];

/** The app's routes that only send the visitor to another screen. */
const REDIRECTS = ["/reminders", "/reminders/new"];

/** The app in the demo's frame: its Telegram and its fetch are the bridges to a stand with the demo's API. */
function openDemo(language: Lang, path: string) {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(MORNING);
  const { host } = testHost(createApi({ language, now: () => Date.now() }), language);
  installTelegram(host);
  vi.stubGlobal("fetch", demoFetch(host, vi.fn()));
  window.history.replaceState(null, "", `/#${path}`);
  render(<App />);
}

async function shown(known: Known): Promise<void> {
  if (typeof known === "object" && !(known instanceof RegExp)) await screen.findByDisplayValue(known.value);
  else expect((await screen.findAllByText(known)).length).toBeGreaterThan(0);
}

describe("the demo's screens", () => {
  it("are all the app's screens: a new route of the app has to come here too", () => {
    const screens = ROUTES.map((route) => route.path).filter((path) => !REDIRECTS.includes(path));
    expect(screens).toHaveLength(22);
    expect(SCREENS.map(([route]) => route)).toEqual(screens);
  });

  for (const language of ["ru", "en"] as const) {
    it.each(SCREENS)(`open in ${language === "ru" ? "Russian" : "English"} without an error: %s`, async (_, path, ru, en) => {
      openDemo(language, path);
      await shown(language === "ru" ? ru : en);
      await waitFor(() => expect(document.querySelector("[aria-busy='true'], .skeleton")).toBeNull());
      expect(document.querySelector(".error-state")).toBeNull();
      expect(window.location.hash).toBe(`#${path}`);
    });
  }
});
