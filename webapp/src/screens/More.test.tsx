import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Toasts } from "../components/Toasts";
import { installTelegram } from "../test/fakeTelegram";
import { me } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { MoreScreen, REPO_URL } from "./More";

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

  it("shows the version and opens the source code", async () => {
    const app = installTelegram();
    mockApi({ "GET /me": me, "GET /health": { status: "ok", version: "2.1.0", commit: null } });
    renderWithApp(<MoreScreen />, { path: "/more" });
    expect(await screen.findByText("Версия 2.1.0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Исходный код на GitHub" }));
    expect(app.openLink).toHaveBeenCalledWith(REPO_URL);
  });
});
