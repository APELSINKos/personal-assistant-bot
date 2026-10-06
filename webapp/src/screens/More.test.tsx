import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { keys } from "../api/queries";
import type { City, Me, WeatherCity } from "../api/types";
import { Toasts } from "../components/Toasts";
import { GEONAMES_URL, LICENCE_URL, OPEN_METEO_URL } from "../lib/links";
import { installTelegram } from "../test/fakeTelegram";
import { me, scheduleSource, tula } from "../test/fixtures";
import { mockApi, type ApiCall } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoreScreen, REPO_URL } from "./More";

const HEALTH = { status: "ok", version: "2.1.0", commit: null };
const UNAVAILABLE = {
  status: 503, body: { status: 503, code: "upstream_unavailable", title: "Upstream service unavailable" },
};

/** PATCH /me answers only when the test calls `answer`, so the screen can be seen in between. */
function heldPatches() {
  const held: ((reply: unknown) => void)[] = [];
  const handler = () => new Promise((resolve) => held.push(resolve));
  const answer = (reply: unknown) => {
    act(() => held.shift()?.(reply));
  };
  return { handler, held, answer };
}

const KAZAN: City = {
  name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow",
  geo_id: 551487,
};
const KAZAN_FOUND = "Казань, Татарстан, Россия";
const SEARCH_KAZAN = "GET /cities?q=%D0%9A%D0%B0%D0%B7";
const SOCHI: WeatherCity = {
  id: 4, name: "Сочи", admin: "Краснодарский край", country: "Россия", lat: 43.6, lon: 39.73,
  timezone: "Europe/Moscow", geo_id: 491422,
};
const DUPLICATE = {
  status: 422,
  body: { status: 422, code: "validation_error", title: "Invalid input", field: "city", reason: "duplicate" },
};
const NO_ROOM = { status: 409, body: { status: 409, code: "limit_reached", title: "Limit reached", entity: "city", limit: 4 } };

/** The extra cities as the server keeps them: a city added is listed, one deleted is not. */
function extraCities(start: WeatherCity[]) {
  let list = [...start];
  let next = 10;
  return {
    "GET /me/cities": () => ({ body: list }),
    "POST /me/cities": ({ body }: { body: unknown }) => {
      const city = { ...(body as Omit<WeatherCity, "id">), id: next };
      next += 1;
      list = [...list, city];
      return { status: 201, body: city };
    },
    ...Object.fromEntries(
      start.map((city) => [
        `DELETE /me/cities/${city.id}`,
        () => {
          list = list.filter((kept) => kept.id !== city.id);
          return { status: 204 };
        },
      ]),
    ),
  };
}

function showMore(routes: Record<string, unknown>) {
  const app = installTelegram();
  const api = mockApi({ "GET /me": me, "GET /health": HEALTH, "GET /me/cities": [tula], ...routes });
  return { app, ...api, ...renderWithApp(<><MoreScreen /><Toasts /></>, { path: "/more" }) };
}

const sent = (calls: ApiCall[], method: string) => calls.filter((call) => call.method === method);

/** Opens the search with one of the two buttons and types a query into it. */
async function search(button: "Сменить домашний" | "Добавить город", query: string) {
  fireEvent.click(await screen.findByRole("button", { name: button }));
  const label = button === "Сменить домашний" ? "Новый домашний город" : "Какой город добавить";
  fireEvent.change(screen.getByRole("searchbox", { name: label }), { target: { value: query } });
}

/** Chooses a found city as a tap or a key does, focus first (a click in jsdom moves no focus). */
async function choose(name: string) {
  const result = await screen.findByRole("button", { name });
  act(() => result.focus());
  fireEvent.click(result);
  return result;
}

describe("More → Cities", () => {
  it("shows the home city with what keeps its time, and the extra cities; the search waits to be asked for", async () => {
    showMore({});
    const card = (await screen.findByRole("heading", { name: "Города" })).closest("section") as HTMLElement;
    expect(within(card).getByText("🏠 Москва")).toBeInTheDocument();
    expect(within(card).getByText("по его времени приходят напоминания и сводка")).toBeInTheDocument();
    expect(await within(card).findByText("Тула")).toBeInTheDocument();
    expect(within(card).getByText("Тульская область, Россия")).toBeInTheDocument();
    expect(within(card).queryByRole("searchbox")).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Сменить домашний" })).toHaveAttribute("aria-expanded", "false");
    expect(within(card).getByRole("button", { name: "Добавить город" })).toBeEnabled();
    expect(within(card).queryByText("До 5 городов вместе с домашним")).not.toBeInTheDocument();
  });

  it("opens the search with the button that asks for it and hides it with the same button", async () => {
    showMore({ [SEARCH_KAZAN]: [KAZAN] });
    const home = await screen.findByRole("button", { name: "Сменить домашний" });
    const add = screen.getByRole("button", { name: "Добавить город" });
    fireEvent.click(home);
    const field = screen.getByRole("searchbox", { name: "Новый домашний город" });
    expect(field).toHaveFocus();
    expect(home).toHaveAttribute("aria-expanded", "true");
    expect(home).toHaveAttribute("aria-controls", field.closest(".city-search")?.id);
    fireEvent.change(field, { target: { value: "Каз" } });
    expect(await screen.findByRole("button", { name: KAZAN_FOUND })).toBeInTheDocument();

    // The other button turns the open search to its own use; what was typed stays.
    fireEvent.click(add);
    const toAdd = screen.getByRole("searchbox", { name: "Какой город добавить" });
    expect(toAdd).toHaveValue("Каз");
    expect(toAdd).toHaveFocus();
    expect(home).toHaveAttribute("aria-expanded", "false");
    expect(add).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(add);
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(add).toHaveAttribute("aria-expanded", "false");
    // A click that does not focus its button (Safari) would leave the focus nowhere.
    expect(add).toHaveFocus();
    fireEvent.click(add); // a search hidden starts anew
    expect(screen.getByRole("searchbox", { name: "Какой город добавить" })).toHaveValue("");
  });

  it("changes the home city from its search, closes the search and says it is saved", async () => {
    const { calls } = showMore({ [SEARCH_KAZAN]: [KAZAN], "PUT /me/city": { ...me, city: KAZAN } });
    await search("Сменить домашний", "Каз");
    await choose(KAZAN_FOUND);
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(calls).toContainEqual({
      method: "PUT", path: "/me/city",
      body: { name: "Казань", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow", geo_id: 551487 },
    });
    expect(screen.getByText("🏠 Казань")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: KAZAN_FOUND })).not.toBeInTheDocument();
    // The search took the focus with it: it goes back to the button that opened the search.
    expect(screen.getByRole("button", { name: "Сменить домашний" })).toHaveFocus();
    expect(sent(calls, "POST")).toEqual([]);
  });

  it("adds a city from its search, and the home city stays as it is", async () => {
    const { calls } = showMore({ [SEARCH_KAZAN]: [KAZAN], ...extraCities([tula]) });
    await search("Добавить город", "Каз");
    await choose(KAZAN_FOUND);
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить город" })).toHaveFocus();
    expect(calls).toContainEqual({
      method: "POST", path: "/me/cities",
      body: {
        name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow",
        geo_id: 551487,
      },
    });
    const card = screen.getByRole("heading", { name: "Города" }).closest("section") as HTMLElement;
    const list = within(card).getByRole("list");
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(2));
    expect(within(list).getByText("Казань")).toBeInTheDocument();
    expect(within(list).getByText("Татарстан, Россия")).toBeInTheDocument();
    expect(screen.getByText("🏠 Москва")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(sent(calls, "PUT")).toEqual([]);
  });

  it("keeps the search open when the server refuses a city, and says why", async () => {
    let refusal: typeof DUPLICATE | typeof NO_ROOM = DUPLICATE;
    showMore({ [SEARCH_KAZAN]: [KAZAN], "POST /me/cities": () => refusal });
    await search("Добавить город", "Каз");
    const result = await choose(KAZAN_FOUND);
    expect(await screen.findByText("Этот город уже в списке")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Какой город добавить" })).toHaveValue("Каз");
    expect(result).toHaveFocus();

    // Added in the bot meanwhile: the fifth city with the home one.
    refusal = NO_ROOM;
    await waitFor(() => expect(result).not.toHaveAttribute("aria-disabled"));
    fireEvent.click(result);
    expect(await screen.findByText("Уже 5 городов вместе с домашним — удали лишний")).toBeInTheDocument();
  });

  it("lets no second city go while the first is being saved", async () => {
    let answer!: (reply: unknown) => void;
    const kaluga: City = {
      name: "Калуга", admin: "Калужская область", country: "Россия", lat: 54.51, lon: 36.26,
      timezone: "Europe/Moscow", geo_id: 553915,
    };
    const { calls } = showMore({
      "GET /cities?q=%D0%9A%D0%B0": [KAZAN, kaluga],
      "POST /me/cities": () => new Promise((resolve) => (answer = resolve)),
    });
    await search("Добавить город", "Ка");
    const chosen = await choose(KAZAN_FOUND);
    const other = screen.getByRole("button", { name: "Калуга, Калужская область, Россия" });
    await waitFor(() => expect(other).toHaveAttribute("aria-disabled", "true"));
    // Off, yet not `disabled`: a disabled button would drop the focus.
    expect(chosen).toHaveAttribute("aria-disabled", "true");
    expect(chosen).toBeEnabled();
    expect(chosen).toHaveFocus();
    fireEvent.click(chosen);
    fireEvent.click(other);
    act(() => answer({ status: 201, body: { ...KAZAN, id: 5 } }));
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(sent(calls, "POST")).toHaveLength(1);
  });

  it("deletes an extra city without a question", async () => {
    const { app, calls } = showMore(extraCities([tula, SOCHI]));
    const row = (await screen.findByText("Тула")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Удалить город" }));
    await waitFor(() => expect(screen.queryByText("Тула")).not.toBeInTheDocument());
    expect(sent(calls, "DELETE")).toEqual([{ method: "DELETE", path: "/me/cities/3", body: undefined }]);
    expect(screen.getByText("Сочи")).toBeInTheDocument();
    expect(app.showConfirm).not.toHaveBeenCalled();
  });

  it("turns «Добавить город» off at four extra cities and says why under it", async () => {
    const four = [1, 2, 3, 4].map((id) => ({ ...tula, id, name: `Город ${id}`, geo_id: id }));
    showMore({ "GET /me/cities": four });
    const add = await screen.findByRole("button", { name: "Добавить город" });
    await waitFor(() => expect(add).toBeDisabled());
    expect(add).toHaveAccessibleDescription("До 5 городов вместе с домашним");
    expect(screen.getByRole("button", { name: "Сменить домашний" })).toBeEnabled();
  });

  it("closes the search for adding once the list has filled up", async () => {
    const three = [1, 2, 3].map((id) => ({ ...tula, id, name: `Город ${id}`, geo_id: id }));
    const { client } = showMore({ "GET /me/cities": three });
    fireEvent.click(await screen.findByRole("button", { name: "Добавить город" }));
    expect(screen.getByRole("searchbox", { name: "Какой город добавить" })).toBeInTheDocument();
    // A fourth one, added in the bot, comes with a refresh.
    await act(async () => {
      client.setQueryData<WeatherCity[]>(keys.weatherCities, [...three, { ...tula, id: 4, name: "Город 4", geo_id: 4 }]);
      await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
    });
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить город" })).toBeDisabled();
    // The focus was in the search, and the button that opened it is off: the other one takes it.
    expect(screen.getByRole("button", { name: "Сменить домашний" })).toHaveFocus();
  });

  it("gives the focus to «Сменить домашний» when the city added is the fourth", async () => {
    const three = [1, 2, 3].map((id) => ({ ...tula, id, name: `Город ${id}`, geo_id: id }));
    showMore({ [SEARCH_KAZAN]: [KAZAN], ...extraCities(three) });
    await screen.findByText("Город 3");
    await search("Добавить город", "Каз");
    await choose(KAZAN_FOUND);
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить город" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сменить домашний" })).toHaveFocus();
  });

  it("moves the focus to «Сменить домашний» when «Добавить город» turns off under it", async () => {
    const three = [1, 2, 3].map((id) => ({ ...tula, id, name: `Город ${id}`, geo_id: id }));
    const { client } = showMore({ "GET /me/cities": three });
    await screen.findByText("Город 3");
    const add = screen.getByRole("button", { name: "Добавить город" });
    act(() => add.focus());
    await act(async () => {
      client.setQueryData<WeatherCity[]>(keys.weatherCities, [...three, { ...tula, id: 4, name: "Город 4", geo_id: 4 }]);
      await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
    });
    expect(add).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сменить домашний" })).toHaveFocus();
  });

  it("offers a retry when the extra cities cannot be read, and keeps the rest of the screen", async () => {
    let refused = true;
    showMore({
      "GET /me/cities": () =>
        refused ? { status: 429, body: { status: 429, code: "rate_limited", title: "Too many requests" } } : { body: [tula] },
    });
    const card = (await screen.findByRole("heading", { name: "Города" })).closest("section") as HTMLElement;
    const retry = await within(card).findByRole("button", { name: "Повторить" });
    expect(within(card).getByText("🏠 Москва")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Утренняя сводка" })).toBeInTheDocument();
    refused = false;
    fireEvent.click(retry);
    expect(await within(card).findByText("Тула")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
  });

  it("says so when the city search is unavailable", async () => {
    const { client } = showMore({ [SEARCH_KAZAN]: UNAVAILABLE });
    client.setQueryDefaults(["cities"], { retry: false }); // the app retries a 503 twice first
    await search("Сменить домашний", "Каз");
    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
  });

  it("reads out what each city search found, in a region that was there before it", async () => {
    showMore({ [SEARCH_KAZAN]: [KAZAN], "GET /cities?q=qqq": [] });
    fireEvent.click(await screen.findByRole("button", { name: "Добавить город" }));
    const field = screen.getByRole("searchbox", { name: "Какой город добавить" });
    // A screen reader reads out changes only in a region it already listens to.
    const regions = screen.getAllByRole("status");
    fireEvent.change(field, { target: { value: "Каз" } });
    const region = (await screen.findByText("Найдено городов: 1")).closest('[role="status"]');
    expect(regions).toContain(region);
    fireEvent.change(field, { target: { value: "qqq" } });
    await waitFor(() => expect(region).toHaveTextContent("Ничего не нашлось"));
  });

  it("counts a search in characters as the server does, and asks for none it would refuse", async () => {
    const { calls } = showMore({ "GET /cities": [KAZAN] });
    const searches = () => calls.filter((call) => call.path.startsWith("/cities"));
    fireEvent.click(await screen.findByRole("button", { name: "Добавить город" }));
    const field = screen.getByRole("searchbox", { name: "Какой город добавить" });

    fireEvent.change(field, { target: { value: "🏙" } }); // one character in two UTF-16 units
    // Longer than the 300 ms the field waits for more typing: a search would have gone out by now.
    await act(() => new Promise((resolve) => setTimeout(resolve, 450)));
    expect(searches()).toEqual([]);

    fireEvent.change(field, { target: { value: "🏙".repeat(50) } });
    expect(await screen.findByRole("button", { name: KAZAN_FOUND })).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "false");
    expect(searches()).toHaveLength(1);

    fireEvent.change(field, { target: { value: "🏙".repeat(51) } });
    expect(screen.getByText("51/50")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("51/50");
    expect(screen.queryByRole("button", { name: KAZAN_FOUND })).not.toBeInTheDocument();
    await act(() => new Promise((resolve) => setTimeout(resolve, 450)));
    expect(searches()).toHaveLength(1);
  });
});

describe("More", () => {
  it("changes the digest and the language", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /health": { status: "ok", version: "2.1.0", commit: null },
      "PATCH /me": ({ body }: { body: unknown }) => {
        const patch = body as Record<string, unknown>;
        return {
          body: {
            ...me,
            language_setting: (patch.language as string | undefined) ?? me.language_setting,
            morning: { ...me.morning, enabled: (patch.morning_enabled as boolean | undefined) ?? true },
          },
        };
      },
    });
    renderWithApp(<MoreScreen />, { path: "/more" });
    fireEvent.click(await screen.findByRole("switch", { name: "Утренняя сводка" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PATCH", path: "/me", body: { morning_enabled: false } }),
    );
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(calls).toContainEqual({ method: "PATCH", path: "/me", body: { language: "en" } });
  });

  it("flips the digest switch at once and puts it back when saving fails", async () => {
    installTelegram();
    const patch = heldPatches();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "PATCH /me": patch.handler });
    renderWithApp(<><MoreScreen /><Toasts /></>, { path: "/more" });
    const toggle = await screen.findByRole("switch", { name: "Утренняя сводка" });
    fireEvent.click(toggle);
    await waitFor(() => expect(patch.held).toHaveLength(1));
    expect(toggle).not.toBeChecked(); // before the server has answered
    expect(screen.getByLabelText("Время сводки")).toBeDisabled();
    patch.answer(UNAVAILABLE);
    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
    await waitFor(() => expect(toggle).toBeChecked());
  });

  it("keeps the settings on screen when a refresh of the profile fails", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "GET /me/cities": [] });
    const { client } = renderWithApp(<MoreScreen />, { path: "/more" });
    expect(await screen.findByRole("switch", { name: "Утренняя сводка" })).toBeInTheDocument();
    mockApi({ "GET /me": { status: 429, body: { status: 429, code: "rate_limited" } } });
    await act(async () => {
      await client.refetchQueries({ queryKey: ["me"] });
      await new Promise((resolve) => setTimeout(resolve, 0)); // observers hear of it a tick later
    });
    expect(screen.getByRole("switch", { name: "Утренняя сводка" })).toBeChecked();
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
  });

  it("presses a language button at once", async () => {
    installTelegram();
    const patch = heldPatches();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "PATCH /me": patch.handler });
    const { client } = renderWithApp(<MoreScreen />, { path: "/more" });
    fireEvent.click(await screen.findByRole("button", { name: "English" }));
    await waitFor(() => expect(patch.held).toHaveLength(1));
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Авто" })).toHaveAttribute("aria-pressed", "false");
    // The interface language is the server's to decide; it does not switch before the answer.
    expect(client.getQueryData<Me>(["me"])?.language).toBe("ru");
  });

  it("saves the morning time once, with the final value", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /health": HEALTH,
      "PATCH /me": ({ body }: { body: unknown }) => ({
        body: { ...me, morning: { ...me.morning, time: (body as { morning_time: string }).morning_time } },
      }),
    });
    renderWithApp(<MoreScreen />, { path: "/more" });
    const field = await screen.findByLabelText("Время сводки");
    const patches = () => calls.filter((call) => call.method === "PATCH").map((call) => call.body);
    // A desktop time field reports every keystroke as a complete time.
    for (const value of ["00:00", "09:00", "09:03", "09:30"]) {
      fireEvent.change(field, { target: { value } });
    }
    expect(field).toHaveValue("09:30");
    await waitFor(() => expect(patches()).toEqual([{ morning_time: "09:30" }]), { timeout: 2000 });
    fireEvent.blur(field); // the same time as the saved one: nothing to send
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(patches()).toHaveLength(1);
    fireEvent.change(field, { target: { value: "07:15" } });
    fireEvent.blur(field); // leaving the field saves at once
    await waitFor(() => expect(patches()).toHaveLength(2), { timeout: 300 });
    expect(patches()[1]).toEqual({ morning_time: "07:15" });
  });

  it("changes the currency of the accounts, saying the amounts stay", async () => {
    installTelegram();
    const { calls } = mockApi({ "GET /me": me, "GET /health": HEALTH, "PATCH /me": { ...me, currency: "KZT" } });
    renderWithApp(<MoreScreen />, { path: "/more" });
    const select = await screen.findByLabelText("Валюта");
    expect(select).toHaveValue("RUB");
    expect(screen.getByRole("option", { name: "₽ RUB — Российский рубль" })).toBeInTheDocument();
    expect(screen.getByText("Суммы уже сделанных записей не пересчитываются — меняется только знак.")).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "KZT" } });
    await waitFor(() => expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ currency: "KZT" }));
    expect(select).toHaveValue("KZT");
  });

  it("names the sources of the weather and of the city names, each opening its site", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /health": HEALTH });
    renderWithApp(<MoreScreen />, { path: "/more" });
    const card = (await screen.findByRole("heading", { name: "Данные" })).closest("section") as HTMLElement;
    expect(card).toHaveTextContent(
      "Погода — open-meteo.com, названия городов — geonames.org; лицензия CC BY 4.0 " +
        "(creativecommons.org/licenses/by/4.0), приложение округляет данные и добавляет советы.",
    );
    fireEvent.click(within(card).getByRole("button", { name: "open-meteo.com" }));
    fireEvent.click(within(card).getByRole("button", { name: "geonames.org" }));
    fireEvent.click(within(card).getByRole("button", { name: "creativecommons.org/licenses/by/4.0" }));
    expect(app.openLink).toHaveBeenNthCalledWith(1, OPEN_METEO_URL);
    expect(app.openLink).toHaveBeenNthCalledWith(2, GEONAMES_URL);
    expect(app.openLink).toHaveBeenNthCalledWith(3, LICENCE_URL);
  });

  it("names the sources in English too", async () => {
    installTelegram();
    mockApi({ "GET /me": { ...me, language: "en" }, "GET /health": HEALTH, "GET /me/cities": [tula] });
    renderWithApp(<MoreScreen />, { path: "/more", lang: "en" });
    const card = (await screen.findByRole("heading", { name: "Data" })).closest("section") as HTMLElement;
    expect(card).toHaveTextContent("the app rounds the data and adds tips.");
    expect(screen.getByText("reminders and the morning digest follow its time")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change home city" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add a city" }));
    expect(screen.getByRole("searchbox", { name: "City to add" })).toBeInTheDocument();
  });

  it("shows the version and opens the source code", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /health": { status: "ok", version: "2.1.0", commit: null } });
    renderWithApp(<MoreScreen />, { path: "/more" });
    expect(await screen.findByText("Версия 2.1.0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Исходный код на GitHub" }));
    expect(app.openLink).toHaveBeenCalledWith(REPO_URL);
  });
});

describe("More schedule entry", () => {
  it("leads to the schedule and tells what is connected", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "GET /schedule": { source: scheduleSource } });
    const { unmount } = renderWithApp(<MoreScreen />, { path: "/more" });
    const entry = await screen.findByRole("link", { name: "🎓 Расписание пар ИКБО-63-24" });
    expect(entry).toHaveAttribute("href", "/more/schedule");
    unmount();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "GET /schedule": { source: null } });
    renderWithApp(<MoreScreen />, { path: "/more" });
    expect(await screen.findByRole("link", { name: "🎓 Расписание пар Не подключено" })).toBeInTheDocument();
  });
});
