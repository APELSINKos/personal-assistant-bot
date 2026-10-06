import type { ClassesWeather, Forecast, TodayLesson } from "../api/types";
import type { Lang } from "../i18n";
import type { Dict } from "../i18n/ru";
import { capitalize, formatTemp, parseIsoDate, shownChance } from "./format";

/**
 * The weather of the way to classes names a chance from this much, as the bot does
 * (weather.CLASSES_CHANCE): a lower one is no reason to take an umbrella to a lecture.
 */
export const CLASSES_CHANCE = 30;

/**
 * A cell of the 24-hour strip, as wide as weather.css makes it: 5½ cells show on a 320 px phone,
 * and the cut sixth tells that the strip scrolls.
 */
export const CELL_WIDTH = 52;

/** The temperature curve over the strip's cells. */
export const CURVE_HEIGHT = 40;

// Room over the highest point and under the lowest, so the 2 px line is never cut.
const CURVE_PAD = 6;

/** One cell of the strip: now, or an hour of the forecast. */
export interface StripCell {
  time: string;
  emoji: string;
  description: string;
  temperature: number | null;
  /** The forecast's own chance: shownChance decides whether it is said. */
  chance: number | null;
}

/**
 * The strip's cells: «Сейчас» with the weather now and the chance of the hour going on, then the
 * hours after it as the server counted them on the city's clock.
 */
export function stripCells(forecast: Forecast, nowLabel: string): StripCell[] {
  const { now } = forecast;
  return [
    {
      time: nowLabel,
      emoji: now.emoji,
      description: now.description,
      temperature: now.temperature,
      chance: now.precip_chance,
    },
    ...forecast.hours.map((hour) => ({
      time: hour.time,
      emoji: hour.emoji,
      description: hour.description,
      temperature: hour.temperature,
      chance: hour.precip_chance,
    })),
  ];
}

export type Point = readonly [x: number, y: number];

/** A coordinate of a path, to a tenth of a pixel. */
function coordinate(value: number): string {
  return String(Math.round(value * 10) / 10);
}

/**
 * A smooth line through points that go left to right, which never swings past them (Steffen's
 * monotone cubic): a curve of temperatures shows no warmth or cold that the hours do not have.
 */
export function smoothPath(points: readonly Point[]): string {
  const [head, ...rest] = points;
  if (head === undefined) return "";
  // The slope of each piece between two neighbours.
  const slopes = rest.map(([x, y], index) => {
    const [fromX, fromY] = points[index] ?? head;
    return (y - fromY) / (x - fromX);
  });
  // The tangent at each point: flat at a peak or a dip, never steeper than its pieces allow.
  const tangents = points.map((_, index) => {
    const before = slopes[index - 1];
    const after = slopes[index];
    if (before === undefined) return after ?? 0;
    if (after === undefined) return before;
    const sign = Math.sign(before) + Math.sign(after);
    return sign * Math.min(Math.abs(before), Math.abs(after), Math.abs(before + after) / 4);
  });
  let path = `M${coordinate(head[0])},${coordinate(head[1])}`;
  rest.forEach(([x, y], index) => {
    const [fromX, fromY] = points[index] ?? head;
    const third = (x - fromX) / 3;
    const out = fromY + (tangents[index] ?? 0) * third;
    const into = y - (tangents[index + 1] ?? 0) * third;
    path += ` C${coordinate(fromX + third)},${coordinate(out)} ${coordinate(x - third)},${coordinate(into)}`;
    path += ` ${coordinate(x)},${coordinate(y)}`;
  });
  return path;
}

export interface Curve {
  /** The line through the cells' temperatures. */
  line: string;
  /** The same line closed down to the bottom, to shade under it. */
  area: string;
  /** Each cell's point, by the cell's index; null for a cell without a temperature. */
  points: (Point | null)[];
  low: number;
  high: number;
}

/**
 * The temperature curve over the strip: a point over the middle of each cell that has a
 * temperature, the warmest at the top. Null under two of them: no line goes through one point.
 */
export function temperatureCurve(temperatures: readonly (number | null)[]): Curve | null {
  const known = temperatures.filter((value): value is number => value !== null);
  if (known.length < 2) return null;
  const low = Math.min(...known);
  const high = Math.max(...known);
  const span = high - low;
  const points = temperatures.map((value, index): Point | null => {
    if (value === null) return null;
    const y = span === 0 ? CURVE_HEIGHT / 2 : CURVE_PAD + ((high - value) / span) * (CURVE_HEIGHT - 2 * CURVE_PAD);
    return [(index + 0.5) * CELL_WIDTH, y];
  });
  const drawn = points.filter((point): point is Point => point !== null);
  const line = smoothPath(drawn);
  const [firstX] = drawn[0] ?? [0];
  const [lastX] = drawn.at(-1) ?? [0];
  const bottom = coordinate(CURVE_HEIGHT);
  const area = `${line} L${coordinate(lastX)},${bottom} L${coordinate(firstX)},${bottom} Z`;
  return { line, area, points, low, high };
}

/**
 * Where a day's range lies on the week's scale, in percent of it: how far its lowest temperature
 * is from the left, and how much of the scale the range takes.
 */
export function rangeBar(
  low: number, high: number, weekLow: number, weekHigh: number,
): { from: number; width: number } {
  const span = weekHigh - weekLow;
  if (span <= 0) return { from: 0, width: 100 };
  const percent = (value: number) => Math.round((value / span) * 1000) / 10;
  return { from: percent(low - weekLow), width: percent(high - low) };
}

interface DayWords {
  today: string;
  tomorrow: string;
}

function dayOf(iso: string, lang: Lang, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(lang, { timeZone: "UTC", ...options }).format(parseIsoDate(iso));
}

/**
 * A day of the week's forecast by its place: the first is the city's today, the next tomorrow,
 * then «ср, 7 окт.».
 */
export function weekDayLabel(index: number, iso: string, lang: Lang, words: DayWords): string {
  if (index === 0) return words.today;
  if (index === 1) return words.tomorrow;
  return dayOf(iso, lang, { weekday: "short", day: "numeric", month: "short" });
}

/** The same day said in full, for a screen reader: «Среда, 7 октября». */
export function weekDayName(index: number, iso: string, lang: Lang, words: DayWords): string {
  if (index === 0) return words.today;
  if (index === 1) return words.tomorrow;
  return capitalize(dayOf(iso, lang, { weekday: "long", day: "numeric", month: "long" }));
}

/**
 * The wind in whole metres a second, and its gusts when they blow harder than the wind itself;
 * null without a wind to tell of.
 */
export function windWords(wind: number | null, gusts: number | null): { speed: string; gusts: string | null } | null {
  if (wind === null) return null;
  const speed = Math.round(wind);
  const peak = gusts === null ? null : Math.round(gusts);
  return { speed: String(speed), gusts: peak !== null && peak > speed ? String(peak) : null };
}

/** When the day's classes begin and end, in milliseconds: the earliest start and the latest end. */
function classesSpan(lessons: readonly TodayLesson[]): { start: number; end: number } {
  return {
    start: Math.min(...lessons.map((lesson) => Date.parse(lesson.starts_at))),
    end: Math.max(...lessons.map((lesson) => Date.parse(lesson.ends_at))),
  };
}

/**
 * The next moment the card of the day's classes changes by itself: the first class begins (the way
 * there is behind), the last one ends (the classes are over). Null when neither is ahead.
 */
export function nextClassesChange(lessons: readonly TodayLesson[], now: number): number | null {
  if (lessons.length === 0) return null;
  const { start, end } = classesSpan(lessons);
  if (now < start) return start;
  return now < end ? end : null;
}

/**
 * The weather of the way to classes and back, as much of it as is still ahead: the whole line
 * before the first class, «После пар» once it has begun or without the forecast of its hour, and
 * nothing once the last one has ended or without the forecast of its end. The server gives the
 * whole day's; the card asks again at each moment nextClassesChange names.
 */
export function classesLine(
  weather: ClassesWeather | null, lessons: readonly TodayLesson[], t: Dict, now: number = Date.now(),
): string | null {
  if (weather === null || weather.end_temp === null || lessons.length === 0) return null;
  const { start, end } = classesSpan(lessons);
  if (now >= end) return null;
  const after = t.today.withChance(formatTemp(weather.end_temp), shownChance(weather.end_chance, CLASSES_CHANCE));
  if (now >= start || weather.start_temp === null) return t.today.classesAfter(weather.end, after);
  const way = t.today.withChance(formatTemp(weather.start_temp), shownChance(weather.start_chance, CLASSES_CHANCE));
  return t.today.classes(weather.start, way, weather.end, after);
}
