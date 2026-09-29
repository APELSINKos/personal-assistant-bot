import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { toast } from "./components/toastStore";
import { me } from "./test/fixtures";
import { installTelegram } from "./test/fakeTelegram";
import { mockApi } from "./test/mockApi";
import { act } from "react";

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
});
