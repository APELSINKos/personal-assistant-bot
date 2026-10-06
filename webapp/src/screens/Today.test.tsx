import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { keys } from "../api/queries";
import type { ClassesWeather, ForecastDay, TodayLesson } from "../api/types";
import { installTelegram } from "../test/fakeTelegram";
import { habit, today } from "../test/fixtures";
import { mockApi } from "../test/mockApi";
import { renderWithApp } from "../test/render";
import { TodayScreen } from "./Today";

// The visible text is matched as Testing Library normalises it: a plain space where the app keeps
// a percent on the number's line with a no-break one.

describe("Today", () => {
  it("shows the whole day", async () => {
    installTelegram();
    mockApi({ "GET /today": today });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("28")).toBeInTheDocument();
    expect(screen.getByText(/понедельник/)).toBeInTheDocument();
    expect(screen.getByText(/сентябрь 2026/)).toBeInTheDocument();
    expect(screen.getByText("+10°")).toBeInTheDocument();
    expect(screen.getByText(/Дождь ожидается после 18:00/)).toBeInTheDocument();
    expect(screen.queryByText(/Утром холодно/)).not.toBeInTheDocument();
    expect(screen.getByText("19:30")).toBeInTheDocument();
    expect(screen.getByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.getByText(/🔥 5 дней/)).toBeInTheDocument();
    expect(screen.getByText(/USD 84,20 ₽/)).toBeInTheDocument();
    expect(screen.getByText("📝 4 заметки")).toBeInTheDocument();
    expect(screen.getByText("🔥 Лучшая серия: «Спорт» — 5 дней")).toBeInTheDocument();
  });

  it("names the best streak in English, and only when there is one", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, best_streak: { name: "Sport", count: 1, unit: "days" } } });
    const { unmount } = renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("🔥 Best streak: “Sport” — 1 day")).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...today, best_streak: null } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.queryByText(/Лучшая серия/)).not.toBeInTheDocument();
  });

  it("counts a weekly habit's best streak in weeks", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, best_streak: { name: "Бег", count: 3, unit: "weeks" } } });
    const { unmount } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("🔥 Лучшая серия: «Бег» — 3 недели")).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...today, best_streak: { name: "Run", count: 1, unit: "weeks" } } });
    renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("🔥 Best streak: “Run” — 1 week")).toBeInTheDocument();
  });

  it("counts each habit's streak in its own unit", async () => {
    installTelegram();
    const weekly = { ...habit, id: 8, name: "Бег", weekly_goal: 3, streak: 3, streak_unit: "weeks" };
    mockApi({ "GET /today": { ...today, habits: { ...today.habits, items: [habit, weekly] } } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("🔥 3 недели")).toBeInTheDocument();
    expect(screen.getByText("🔥 5 дней")).toBeInTheDocument();
  });

  it("marks a habit with one tap", async () => {
    const app = installTelegram();
    let done: boolean | null = null;
    const { calls } = mockApi({
      "GET /today": () => ({
        body: { ...today, habits: { ...today.habits, items: [{ ...habit, done_today: done }] } },
      }),
      "PUT /habits/7/marks/2026-09-28": ({ body }: { body: unknown }) => {
        done = (body as { done: boolean | null }).done;
        return { body: { ...habit, done_today: done } };
      },
    });
    renderWithApp(<TodayScreen />);
    fireEvent.click(await screen.findByRole("button", { name: /Спорт: без отметки/ }));
    expect(await screen.findByRole("button", { name: /Спорт: выполнено/ })).toBeInTheDocument();
    expect(screen.getByText("Привычки · 1 из 1")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PUT", path: "/habits/7/marks/2026-09-28", body: { done: true } }),
    );
    expect(app.HapticFeedback?.impactOccurred).toHaveBeenCalledWith("light");
  });

  it("test_today_without_weather_and_rates", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, weather: null, rates: null, reminders_today: [] } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Погода временно недоступна")).toBeInTheDocument();
    expect(screen.getByText("Свободный день")).toBeInTheDocument();
    expect(screen.queryByText(/USD/)).not.toBeInTheDocument();
    expect(screen.getByText("Привычки · 0 из 1")).toBeInTheDocument();
  });

  it("offers a retry when the day cannot be loaded", async () => {
    installTelegram();
    mockApi({ "GET /today": { status: 400, body: { status: 400, code: "http_error", title: "Bad" } } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});

describe("Today's weather", () => {
  const tomorrow: ForecastDay = {
    date: "2026-09-29", emoji: "🌧", description: "дождь", tmin: 6.1, tmax: 11.0, precip_chance: 80,
  };

  it("opens the weather screen, and credits Open-Meteo under the card", async () => {
    const app = installTelegram();
    mockApi({ "GET /today": today });
    renderWithApp(<TodayScreen />);
    const card = await screen.findByRole("link", { name: /^Москва/ });
    expect(card).toHaveAttribute("href", "/weather");
    expect(within(card).getByText("+10°")).toBeInTheDocument();
    expect(within(card).getByText("ощущается как +7°")).toBeInTheDocument();
    expect(within(card).getByText("+6…+13°")).toBeInTheDocument();
    expect(within(card).queryByText(/Завтра/)).not.toBeInTheDocument(); // before 17:00 the server sends none
    const credit = screen.getByRole("button", { name: "open-meteo.com" });
    expect(card).not.toContainElement(credit);
    expect(credit.closest("p")).toHaveTextContent("Данные о погоде: open-meteo.com");
    fireEvent.click(credit);
    expect(app.openLink).toHaveBeenCalledWith("https://open-meteo.com/");
  });

  it("opens the weather screen without the weather too, and credits no one then", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, weather: null } });
    renderWithApp(<TodayScreen />);
    const card = await screen.findByRole("link", { name: /Погода временно недоступна/ });
    expect(card).toHaveAttribute("href", "/weather");
    expect(screen.queryByText(/open-meteo/)).not.toBeInTheDocument();
  });

  it("tells tomorrow's weather in the evening, with a chance from 20 %", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, tomorrow } });
    const { unmount } = renderWithApp(<TodayScreen />);
    const card = await screen.findByRole("link", { name: /^Москва/ });
    expect(within(card).getByText("Завтра: 🌧 +6…+11°, 💧 80 %")).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...today, tomorrow: { ...tomorrow, emoji: "☁️", precip_chance: 10 } } });
    renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("Tomorrow: ☁️ +6…+11°")).toBeInTheDocument();
  });
});

describe("Today lessons", () => {
  const lessons: TodayLesson[] = [
    {
      time: "10:40", end: "12:10", title: "Математический анализ", kind: "ЛК", room: "А-16",
      starts_at: "2026-09-28T07:40:00Z", ends_at: "2026-09-28T09:10:00Z",
    },
    {
      time: "12:40", end: "14:10", title: "Разработка баз данных", kind: "ПР", room: null,
      starts_at: "2026-09-28T09:40:00Z", ends_at: "2026-09-28T11:10:00Z",
    },
  ];

  it("lists the day's lessons, then says they are over", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T08:00:00Z")); // 11:00 in Moscow, during the first one
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: "5 неделя" } });
    const { unmount } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Пары · 5 неделя")).toBeInTheDocument();
    expect(screen.getByText("Математический анализ")).toBeInTheDocument();
    expect(screen.getByText("ЛК · 10:40–12:10 · А-16")).toBeInTheDocument();
    expect(screen.getByText("ПР · 12:40–14:10")).toBeInTheDocument();
    unmount();
    vi.setSystemTime(new Date("2026-09-28T11:10:00Z")); // the last one has just ended
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Пары закончились")).toBeInTheDocument();
    expect(screen.queryByText("Математический анализ")).not.toBeInTheDocument();
  });

  it("has no lessons card without lessons today", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, week_label: "5 неделя" } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Привычки · 0 из 1")).toBeInTheDocument();
    expect(screen.queryByText(/^Пары/)).not.toBeInTheDocument();
  });

  it("names the lessons in English", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T08:00:00Z"));
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("Classes")).toBeInTheDocument();
  });

  it("says the lessons are over in English", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T11:10:00Z")); // the last one has just ended
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    renderWithApp(<TodayScreen />, { lang: "en" });
    expect(await screen.findByText("Classes are over for today")).toBeInTheDocument();
    expect(screen.queryByText("Математический анализ")).not.toBeInTheDocument();
  });

  // The tests below fake setTimeout as well as Date: only the card's own timer may re-render it.
  // shouldAdvanceTime lets the query hand its data over (through setTimeout(0)) in real time.
  const fakeClock = (iso: string) => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    vi.setSystemTime(new Date(iso));
  };

  it("says the lessons are over by itself when the last one ends", async () => {
    fakeClock("2026-09-28T11:09:00Z"); // a minute before the last lesson ends
    installTelegram();
    const { calls } = mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: "5 неделя" } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Разработка баз данных")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(90_000);
    });
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
    expect(screen.queryByText("Разработка баз данных")).not.toBeInTheDocument();
    expect(calls.filter((call) => call.path === "/today")).toHaveLength(1); // no refetch behind it
  });

  it("arms its timer again when it fires before the last lesson has ended", async () => {
    fakeClock("2026-09-28T11:09:00Z"); // a minute before the last lesson ends
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Разработка баз данных")).toBeInTheDocument();
    // The wall clock goes back half a minute: the card's timer, armed for a minute, fires early.
    vi.setSystemTime(new Date("2026-09-28T11:08:30Z"));
    act(() => {
      vi.advanceTimersByTime(60_000); // 11:09:30 by the wall clock
    });
    expect(screen.getByText("Разработка баз данных")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(31_000);
    });
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
  });

  it("checks again when the app comes back after the device slept", async () => {
    fakeClock("2026-09-28T11:09:00Z");
    installTelegram();
    const { calls } = mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Разработка баз данных")).toBeInTheDocument();
    // Asleep past the end: the wall clock moved on, the card's uptime-based timer has not fired.
    vi.setSystemTime(new Date("2026-09-28T12:00:00Z"));
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(document.visibilityState).toBe("visible");
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
    expect(calls.filter((call) => call.path === "/today")).toHaveLength(1); // no refetch needed
  });

  it("follows the lessons when they change", async () => {
    fakeClock("2026-09-28T11:09:00Z");
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    const { client } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Разработка баз данных")).toBeInTheDocument();
    // The timetable is refreshed and the last lesson now runs an hour longer, to 15:10 (12:10 UTC).
    const longer = lessons.map((lesson, index) =>
      index === 1 ? { ...lesson, end: "15:10", ends_at: "2026-09-28T12:10:00Z" } : lesson,
    );
    await act(async () => {
      client.setQueryData(keys.today, { ...today, has_schedule: true, lessons: longer, week_label: null });
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      vi.advanceTimersByTime(2 * 60_000); // past the old end
    });
    expect(screen.getByText("Разработка баз данных")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(60 * 60_000); // past the new one
    });
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
  });

  it("judges lessons that arrive after they ended by the time of their arrival", async () => {
    fakeClock("2026-09-28T07:00:00Z"); // 10:00 in Moscow: the first day's lessons are still ahead
    installTelegram();
    mockApi({ "GET /today": { ...today, has_schedule: true, lessons, week_label: null } });
    const { client } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Разработка баз данных")).toBeInTheDocument();
    // The app stays open overnight and is refreshed in the evening of the next day, after that day's classes.
    vi.setSystemTime(new Date("2026-09-29T15:00:00Z"));
    const nextDay = lessons.map((lesson) => ({
      ...lesson,
      starts_at: lesson.starts_at.replace("09-28", "09-29"),
      ends_at: lesson.ends_at.replace("09-28", "09-29"),
    }));
    await act(async () => {
      client.setQueryData(keys.today, {
        ...today, date: "2026-09-29", has_schedule: true, lessons: nextDay, week_label: null,
      });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
  });

  // The whole day's, as the server sends it: 10:40 there, 14:10 back.
  const classesWeather: ClassesWeather = {
    start: "10:40", start_temp: 8.2, start_chance: 40, end: "14:10", end_temp: 11.6, end_chance: 70,
  };
  const withClasses = { ...today, has_schedule: true, lessons, week_label: null, classes_weather: classesWeather };
  const there = "🎓 На пары (10:40): +8°, 💧 40 % · после пар (14:10): +12°, 💧 70 %";
  const back = "🎓 После пар (14:10): +12°, 💧 70 %";

  it("tells the weather of the way there and back, then of the way back, then nothing", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T07:00:00Z")); // 10:00 in Moscow, before the first lesson
    installTelegram();
    mockApi({ "GET /today": withClasses });
    const first = renderWithApp(<TodayScreen />);
    const line = await screen.findByText(there);
    expect(line.closest("section")).toContainElement(screen.getByText("Математический анализ")); // the lessons' card
    first.unmount();
    vi.setSystemTime(new Date("2026-09-28T08:00:00Z")); // during the first lesson
    const during = renderWithApp(<TodayScreen />);
    expect(await screen.findByText(back)).toBeInTheDocument();
    expect(screen.queryByText(/На пары/)).not.toBeInTheDocument();
    during.unmount();
    vi.setSystemTime(new Date("2026-09-28T11:10:00Z")); // the last one has just ended
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Пары закончились")).toBeInTheDocument();
    expect(screen.queryByText(/🎓/)).not.toBeInTheDocument();
  });

  it("tells the way back alone without the forecast of the way there, and nothing without the end's", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-28T07:00:00Z"));
    installTelegram();
    mockApi({ "GET /today": { ...withClasses, classes_weather: { ...classesWeather, start_temp: null } } });
    const { unmount } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText(back)).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...withClasses, classes_weather: null } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Математический анализ")).toBeInTheDocument();
    expect(screen.queryByText(/🎓/)).not.toBeInTheDocument();
  });

  it("drops the way there by itself when the first lesson begins", async () => {
    fakeClock("2026-09-28T07:39:00Z"); // a minute before the first lesson
    installTelegram();
    const { calls } = mockApi({ "GET /today": withClasses });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText(there)).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(90_000);
    });
    expect(screen.getByText(back)).toBeInTheDocument();
    expect(screen.queryByText(/На пары/)).not.toBeInTheDocument();
    expect(calls.filter((call) => call.path === "/today")).toHaveLength(1); // no refetch behind it
    // The same timer then waits for the end of the last lesson.
    act(() => {
      vi.advanceTimersByTime(4 * 60 * 60_000);
    });
    expect(screen.getByText("Пары закончились")).toBeInTheDocument();
    expect(screen.queryByText(/🎓/)).not.toBeInTheDocument();
  });
});

describe("Today's money", () => {
  const money = {
    currency: "RUB", today: 65000, spent: 1240000, budget: 3000000, left: 1760000, per_day: 586666, count: 14,
  };

  it("shows today's spending and the month's budget, and opens the tab", async () => {
    installTelegram();
    mockApi({ "GET /today": { ...today, money } });
    renderWithApp(<TodayScreen />);
    const card = await screen.findByRole("link", { name: /^Деньги/ });
    expect(within(card).getByText("650 ₽")).toBeInTheDocument();
    expect(
      within(card).getByText(
        "Сентябрь: 12 400 ₽ из 30 000 ₽ · осталось 17 600 ₽, по 5 866,66 ₽ в день",
      ),
    ).toBeInTheDocument();
    expect(card).toHaveAttribute("href", "/money");
  });

  it("shows the month without a budget, and nothing without entries or a budget", async () => {
    installTelegram();
    const plain = { ...money, budget: null, left: null, per_day: null };
    mockApi({ "GET /today": { ...today, money: plain } });
    const { unmount } = renderWithApp(<TodayScreen />);
    expect(await screen.findByText("Сентябрь: 12 400 ₽")).toBeInTheDocument();
    unmount();
    mockApi({ "GET /today": { ...today, money: { ...plain, today: 0, spent: 0, count: 0 } } });
    renderWithApp(<TodayScreen />);
    expect(await screen.findByText("📝 4 заметки")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Деньги/ })).not.toBeInTheDocument();
  });
});
