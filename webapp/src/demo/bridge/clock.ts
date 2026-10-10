/**
 * The demo's clock in the app's frame (spec §5.2): with `?at=` the host page runs the clock from
 * that moment, and the frame's Date runs with it, so the app sees the same time as the API. Without
 * `?at=` nothing here touches Date.
 */

/** Date, `offset` ms ahead: `new Date()`, `Date.now()` and `Date()` read the moved clock. */
export function shiftedDate(offset: number, RealDate: DateConstructor = Date): DateConstructor {
  function DemoDate(...args: unknown[]): Date | string {
    const now = RealDate.now() + offset;
    // Called without new, Date gives the time as a string and ignores its arguments.
    if (!new.target) return new RealDate(now).toString();
    return Reflect.construct(RealDate, args.length === 0 ? [now] : args, new.target) as Date;
  }
  DemoDate.prototype = RealDate.prototype;
  return Object.assign(DemoDate, {
    now: () => RealDate.now() + offset,
    parse: RealDate.parse,
    UTC: RealDate.UTC,
  }) as unknown as DateConstructor;
}

/** Moves the frame's Date by the host's offset; null — no `?at=` — leaves Date as it is. */
export function installClock(offset: number | null): void {
  if (offset !== null) window.Date = shiftedDate(offset);
}
