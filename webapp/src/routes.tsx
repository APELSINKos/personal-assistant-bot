import type { ComponentType } from "react";
import { Redirect } from "wouter";
import { CalendarScreen } from "./screens/Calendar";
import { HabitForm } from "./screens/HabitForm";
import { HabitsScreen } from "./screens/Habits";
import { MoreScreen } from "./screens/More";
import { NoteEditor } from "./screens/NoteEditor";
import { NotesScreen } from "./screens/Notes";
import { ReminderForm } from "./screens/ReminderForm";
import { ScheduleScreen } from "./screens/Schedule";
import { TodayScreen } from "./screens/Today";

function ToCalendar() {
  return <Redirect to="/calendar" replace />;
}

export interface AppRoute {
  path: string;
  component: ComponentType;
  /**
   * Telegram's back button appears on this screen and leads to `parent`.
   * Leave unset for a screen that handles the back button itself (e.g. to confirm discarding
   * unsaved edits before leaving) — setting `parent` here would make it navigate away directly,
   * bypassing that screen's own confirmation.
   */
  parent?: string;
  /** Full-screen forms hide the bottom navigation. */
  hideNav?: boolean;
}

/** Screens register themselves here (Tasks 8–10); the first matching path wins. */
export const ROUTES: AppRoute[] = [
  { path: "/", component: TodayScreen },
  { path: "/calendar", component: CalendarScreen },
  { path: "/calendar/new/:date?", component: ReminderForm, hideNav: true },
  { path: "/calendar/:id", component: ReminderForm, hideNav: true },
  { path: "/reminders", component: ToCalendar },
  { path: "/reminders/new", component: ToCalendar },
  { path: "/habits", component: HabitsScreen },
  { path: "/habits/new", component: HabitForm, hideNav: true },
  { path: "/notes", component: NotesScreen },
  { path: "/notes/new", component: NoteEditor, hideNav: true },
  { path: "/notes/:id", component: NoteEditor, hideNav: true },
  { path: "/more", component: MoreScreen },
  { path: "/more/schedule", component: ScheduleScreen, parent: "/more" },
];
