import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
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

const KAZAN = { name: "Казань", admin: "Татарстан", country: "Россия", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow" };

describe("More", () => {
  it("finds and saves a city", async () => {
    installTelegram();
    const { calls } = mockApi({
      "GET /me": me,
      "GET /health": { status: "ok", version: "2.1.0", commit: null },
      "GET /cities?q=%D0%9A%D0%B0%D0%B7": [KAZAN],
      "PUT /me/city": { ...me, city: KAZAN },
    });
    renderWithApp(<><MoreScreen /><Toasts /></>, { path: "/more" });
    expect(await screen.findByText("Москва")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Найти город"), { target: { value: "Каз" } });
    fireEvent.click(await screen.findByRole("button", { name: "Казань, Татарстан, Россия" }));
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(calls).toContainEqual({
      method: "PUT", path: "/me/city",
      body: { name: "Казань", lat: 55.79, lon: 49.12, timezone: "Europe/Moscow" },
    });
    expect(await screen.findByText("Казань")).toBeInTheDocument();
    // Picking a city clears the query; the stale suggestion must vanish right away, not linger
    // for the debounce delay while the search value catches up.
    expect(screen.queryByRole("button", { name: "Казань, Татарстан, Россия" })).not.toBeInTheDocument();
  });

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

  it("says so when the city search is unavailable", async () => {
    installTelegram();
    mockApi({ "GET /me": me, "GET /health": HEALTH, "GET /cities?q=%D0%9A%D0%B0%D0%B7": UNAVAILABLE });
    const { client } = renderWithApp(<MoreScreen />, { path: "/more" });
    client.setQueryDefaults(["cities"], { retry: false }); // the app retries a 503 twice first
    fireEvent.change(await screen.findByLabelText("Найти город"), { target: { value: "Каз" } });
    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
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

  it("shows the version and opens the source code", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /health": { status: "ok", version: "2.1.0", commit: null } });
    renderWithApp(<MoreScreen />, { path: "/more" });
    expect(await screen.findByText("Версия 2.1.0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Исходный код на GitHub" }));
    expect(app.openLink).toHaveBeenCalledWith(REPO_URL);
  });
});
