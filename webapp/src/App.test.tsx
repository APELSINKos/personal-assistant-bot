import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { toast } from "./components/toastStore";
import { ROUTES } from "./routes";
import { me } from "./test/fixtures";
import { installTelegram, oldHeaderColor } from "./test/fakeTelegram";
import { mockApi } from "./test/mockApi";
import { normalizeLaunchHash } from "./telegram";

describe("App shell", () => {
  it("shows the five tabs in the user's language", async () => {
    installTelegram();
    mockApi({ "GET /me": { ...me, language: "en" } });
    render(<App />);
    expect(await screen.findByRole("link", { name: "Reminders" })).toBeInTheDocument();
    for (const name of ["Today", "Habits", "Notes", "More"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("test_expired_session_shows_reopen_screen", async () => {
    installTelegram();
    mockApi({ "GET /me": { status: 401, body: { status: 401, code: "expired_init_data", title: "Unauthorized" } } });
    render(<App />);
    expect(await screen.findByText("Открой приложение заново")).toBeInTheDocument();
    expect(screen.getByText(/Сессия устарела/)).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("explains that the app lives inside Telegram when opened elsewhere", async () => {
    mockApi({});
    render(<App />);
    // Outside Telegram the language comes from the browser (jsdom: en-US).
    expect(await screen.findByText(/works inside Telegram/)).toBeInTheDocument();
  });

  it("translates error toasts", async () => {
    installTelegram();
    mockApi({ "GET /me": me });
    render(<App />);
    await screen.findByRole("navigation");
    act(() => toast({ kind: "error", code: "not_found" }));
    expect(await screen.findByText("Этого уже нет")).toBeInTheDocument();
  });

  it("paints Telegram's bars in the theme colour", async () => {
    const app = installTelegram({ colorScheme: "light" });
    mockApi({ "GET /me": me });
    render(<App />);
    await screen.findByRole("navigation");
    expect(app.setBackgroundColor).toHaveBeenCalledWith("#f7f5f2");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(app.ready).not.toHaveBeenCalled(); // startTelegram() runs in main.tsx, not in <App />
  });

  it("opens on a Telegram client older than 6.9", async () => {
    // Such a client refuses a hex header colour; the app must still come up.
    installTelegram({ setHeaderColor: oldHeaderColor() }, "6.5");
    mockApi({ "GET /me": me });
    render(<App />);
    expect(await screen.findByRole("link", { name: "Привычки" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
  });

  it("applies the theme even before the session is confirmed", async () => {
    // The reopen screen has no `/me` data yet, but it must not flash the wrong theme.
    const app = installTelegram({ colorScheme: "light" });
    mockApi({ "GET /me": { status: 401, body: { status: 401, code: "expired_init_data", title: "Unauthorized" } } });
    render(<App />);
    await screen.findByText("Открой приложение заново");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(app.setBackgroundColor).toHaveBeenCalledWith("#f7f5f2");
  });

  it("normalizes Telegram's launch-parameter hash so a tab is active", async () => {
    window.history.replaceState(null, "", "/#tgWebAppData=abc&tgWebAppVersion=8.0");
    normalizeLaunchHash();
    installTelegram();
    mockApi({ "GET /me": me });
    render(<App />);
    expect(await screen.findByRole("link", { name: "Сегодня" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the BackButton on a route with a parent and navigates there on press", async () => {
    const FakeScreen = () => <p>fake screen</p>;
    ROUTES.push({ path: "/fake", parent: "/", component: FakeScreen });
    try {
      const app = installTelegram();
      mockApi({ "GET /me": me });
      window.history.replaceState(null, "", "/#/fake");
      render(<App />);
      await screen.findByText("fake screen");
      expect(app.BackButton.show).toHaveBeenCalled();
      const onBack = vi.mocked(app.BackButton.onClick).mock.calls.at(-1)?.[0];
      act(() => onBack?.());
      expect(await screen.findByRole("link", { name: "Сегодня" })).toHaveAttribute("aria-current", "page");
    } finally {
      ROUTES.pop();
    }
  });
});
