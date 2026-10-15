/**
 * «Сегодня» (routers/today.py, services/digest.py and views.today_out): the user's day in one answer —
 * the weather, today's reminders, habits and lessons, the notes, the rates, the money of the month,
 * tomorrow's weather from 17:00 and the weather of the way to the classes.
 */
import type { Today } from "../../api/types";
import type { Visit } from "./data";
import { bestStreak, habitOut } from "./habits";
import { json, route, type Route } from "./http";
import { todayMoney } from "./money";
import { noteOrder } from "./notes";
import { todayRates } from "./rates";
import { pending } from "./reminders";
import { lessonsOn, weekLabel } from "./schedule";
import { localClock, localDay, utc, wall } from "./time";
import { classesWeather, dayOut, homeModel, weatherOut } from "./weather";

/** digest.TOMORROW_FROM: tomorrow's weather is shown from this hour of the user's clock. */
const TOMORROW_FROM = 17;

/** digest.part_of_day. */
function partOfDay(hour: number): Today["part_of_day"] {
  if (hour >= 5 && hour <= 11) return "morning";
  if (hour >= 12 && hour <= 16) return "day";
  if (hour >= 17 && hour <= 22) return "evening";
  return "night";
}

function today(visit: Visit): Today {
  const zone = visit.zone();
  const local = wall(zone, visit.now());
  const day = visit.today();
  const w = homeModel(visit);
  const habits = visit.data.habits.map((habit) => habitOut(habit, day));
  const lessons = lessonsOn(visit, day);
  const pinned = noteOrder(visit.data.notes).filter((note) => note.pinned !== null).slice(0, 3);
  return {
    date: day,
    part_of_day: partOfDay(local.hour),
    weather: weatherOut(visit, w),
    reminders_today: pending(visit)
      .filter(({ due }) => localDay(zone, due) === day)
      .map(({ reminder, due }) => ({ id: reminder.id, text: reminder.text, time: localClock(zone, due), due_at: utc(due) })),
    habits: { done: habits.filter((habit) => habit.done_today === true).length, total: habits.length, items: habits },
    notes_count: visit.data.notes.length,
    rates: todayRates(visit),
    best_streak: bestStreak(habits),
    has_schedule: visit.data.source !== null,
    lessons: lessons.map((lesson) => ({
      time: localClock(zone, lesson.start), end: localClock(zone, lesson.end), title: lesson.title, kind: lesson.kind,
      room: lesson.room, starts_at: utc(lesson.start), ends_at: utc(lesson.end),
    })),
    week_label: weekLabel(visit, day),
    money: todayMoney(visit),
    tomorrow: local.hour >= TOMORROW_FROM ? dayOut(w, 1, visit.lang()) : null,
    classes_weather: classesWeather(visit, w, lessons),
    pinned_notes: pinned.map((note) => ({
      id: note.id, text: note.text, done: note.items.filter((item) => item.done).length, total: note.items.length,
    })),
  };
}

export const TODAY: Route[] = [route("GET", "/today", (visit) => json<Today>(today(visit)))];
