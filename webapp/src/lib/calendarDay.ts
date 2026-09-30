/**
 * The calendar day the user was last looking at, kept in memory for the lifetime of the Mini
 * App session (not persisted across a reload). The calendar screen reads it as its starting day
 * and updates it on every pick; the reminder form updates it after a successful save, so leaving
 * the form — with or without saving — returns to the right day instead of always "today".
 */
let day: string | null = null;

export function getCalendarDay(): string | null {
  return day;
}

export function setCalendarDay(iso: string | null): void {
  day = iso;
}
