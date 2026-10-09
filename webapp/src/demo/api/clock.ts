/**
 * The demo's clock (spec §5.2): Moscow's for every visitor, and with `?at=YYYY-MM-DDTHH:MM` it starts
 * from that moment. Moscow has kept UTC+3 all year since 2014.
 */
const MOSCOW = 3 * 60 * 60 * 1000;
const AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

/** The moment `?at=` names on Moscow's clock; null for anything that names no real one. */
export function parseAt(value: string | null): number | null {
  if (value === null || !AT.test(value)) return null;
  const [year = 0, month = 0, day = 0, hour = 0, minute = 0] = value.split(/[-T:]/).map(Number);
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  // Date.UTC rolls 30 February over into March and 24:00 into the next day: only a real moment
  // comes back as it was written.
  return new Date(wall).toISOString().slice(0, 16) === value ? wall - MOSCOW : null;
}

/** The day in Moscow, «2026-10-07». */
export function moscowDay(moment: number): string {
  return new Date(moment + MOSCOW).toISOString().slice(0, 10);
}

/** The hour in Moscow, 0–23. */
export function moscowHour(moment: number): number {
  return new Date(moment + MOSCOW).getUTCHours();
}
