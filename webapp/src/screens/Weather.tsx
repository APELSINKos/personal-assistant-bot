import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type CSSProperties } from "react";
import { useLocation, useRoute } from "wouter";
import { ApiError } from "../api/client";
import { keys, useForecast, useMe, useWeatherCities } from "../api/queries";
import type { Forecast, ForecastDay, WeatherCity } from "../api/types";
import { Card } from "../components/Card";
import { PullToRefresh } from "../components/PullToRefresh";
import { ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { useLang, useT } from "../i18n";
import { capitalize, formatTemp, shownChance } from "../lib/format";
import {
  asEmoji, CELL_WIDTH, CURVE_HEIGHT, rangeBar, stripCells, temperatureCurve, weekDayLabel, weekDayName, windWords,
} from "../lib/weather";
import { haptic } from "../telegram";

/**
 * The city an address names: 0 for the home city (`/weather`), an extra city's id (`/weather/3`),
 * or null when the address names none.
 */
function cityOf(segment: string | undefined): number | null {
  if (segment === undefined) return 0;
  return /^\d{1,15}$/.test(segment) ? Number(segment) : null;
}

/**
 * The weather of the home city or of an extra one, each on its own clock: now and the tips, the
 * next 24 hours, 7 days. One route serves both addresses, so the row of cities stays as it was
 * scrolled when a chip switches the city.
 */
export function WeatherScreen() {
  const [, params] = useRoute("/weather/:id?");
  const id = cityOf(params?.id);
  return id === null ? <CityGone /> : <CityWeather id={id} />;
}

/**
 * A city that is not on the list (any more): deleted in the bot or on another device. The home
 * city's weather instead, with a word why, and the list of cities asked for again.
 */
function CityGone() {
  const t = useT();
  const client = useQueryClient();
  const [, navigate] = useLocation();
  // StrictMode runs an effect twice in development: the toast is said once.
  const told = useRef(false);
  useEffect(() => {
    if (told.current) return;
    told.current = true;
    haptic("error");
    toast({ kind: "error", text: t.weather.cityGone });
    void client.invalidateQueries({ queryKey: keys.weatherCities });
    navigate("/weather", { replace: true });
  }, [client, navigate, t]);
  return <Loader />;
}

function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

function CityWeather({ id }: { id: number }) {
  const t = useT();
  const me = useMe();
  const cities = useWeatherCities();
  const forecast = useForecast(id);
  if (id !== 0 && isGone(forecast.error)) return <CityGone />;
  const home = me.data?.city.name;
  const extra = cities.data ?? [];
  return (
    <PullToRefresh onRefresh={() => Promise.all([forecast.refetch(), cities.refetch()])}>
      <h1 className="screen__title">{t.weather.title}</h1>
      {home !== undefined && extra.length > 0 && <CityChips home={home} cities={extra} current={id} />}
      {forecast.isPending ? (
        <Loader />
      ) : forecast.isLoadingError ? (
        // A failed refresh keeps the forecast shown: only a first load that failed is an error.
        <ErrorState text={t.weather.unavailable} onRetry={() => void forecast.refetch()} />
      ) : (
        // A city of its own: the strip of another city starts again at «Сейчас».
        <ForecastView key={id} forecast={forecast.data} />
      )}
    </PullToRefresh>
  );
}

/** The room CityChips keeps between the pressed chip and the row's edge: the row's scroll-padding-inline. */
const CHIP_ROOM = 4;

/** The home city and the extra ones in one row that scrolls sideways; a chip opens its city in place. */
function CityChips({ home, cities, current }: { home: string; cities: WeatherCity[]; current: number }) {
  const t = useT();
  const [, navigate] = useLocation();
  const row = useRef<HTMLDivElement>(null);
  // Opened by its address (a reload of an extra city's weather), the row starts at its left end,
  // where the pressed chip may not be: the row brings it in then and whenever the city changes, and
  // once more when the fonts are in, as the chips' own font may come after them and widen them.
  // The row alone moves, just enough to show the whole chip, as scrollIntoView with "nearest" would
  // move it; scrollIntoView would also scroll the page and take a reader who has scrolled down back
  // up to the chips. Optional: jsdom has no document.fonts.
  useEffect(() => {
    const show = () => {
      const box = row.current;
      const pressed = box?.querySelector<HTMLElement>('[aria-pressed="true"]');
      if (!box || !pressed) return;
      const edges = box.getBoundingClientRect();
      const chip = pressed.getBoundingClientRect();
      if (chip.left < edges.left + CHIP_ROOM) box.scrollLeft -= edges.left + CHIP_ROOM - chip.left;
      else if (chip.right > edges.right - CHIP_ROOM) box.scrollLeft += chip.right - (edges.right - CHIP_ROOM);
    };
    show();
    void document.fonts?.ready.then(show);
  }, [current]);
  const chips = [{ id: 0, name: `🏠 ${home}` }, ...cities.map((city) => ({ id: city.id, name: city.name }))];
  const open = (id: number) => {
    if (id === current) return;
    haptic("select");
    // In place of the last city: going back leaves the weather instead of walking through the cities.
    navigate(id === 0 ? "/weather" : `/weather/${id}`, { replace: true });
  };
  return (
    <div ref={row} className="city-chips" role="group" aria-label={t.more.cities}>
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          className="city-chip"
          aria-pressed={chip.id === current}
          onClick={() => open(chip.id)}
        >
          {chip.name}
        </button>
      ))}
    </div>
  );
}

function ForecastView({ forecast }: { forecast: Forecast }) {
  return (
    <>
      <NowCard forecast={forecast} />
      <HoursStrip forecast={forecast} />
      <WeekCard days={forecast.days} />
      <Sun forecast={forecast} />
    </>
  );
}

/** Now: the temperature large, what it is like, the wind, the humidity; every tip. */
function NowCard({ forecast }: { forecast: Forecast }) {
  const t = useT();
  const { now, tips } = forecast;
  const wind = windWords(now.wind, now.gusts);
  const facts = [
    now.feels_like === null ? null : t.weather.feels(formatTemp(now.feels_like)),
    wind === null ? null : t.weather.wind(wind.speed, wind.gusts),
    now.humidity === null ? null : t.weather.humidity(Math.round(now.humidity)),
  ].filter((fact) => fact !== null);
  return (
    <Card title={forecast.city.name} index={0}>
      <div className="weather-now">
        <span className="weather-now__temp">{formatTemp(now.temperature)}</span>
        <span className="weather-now__icon" aria-hidden>{asEmoji(now.emoji)}</span>
      </div>
      <p className="weather-now__desc">{capitalize(now.description)}</p>
      {facts.length > 0 && (
        <ul className="weather-facts">
          {facts.map((fact) => <li key={fact}>{fact}</li>)}
        </ul>
      )}
      {tips.length > 0 && (
        <ul className="weather-tips">
          {tips.map((tip, index) => <li key={index}>{tip}</li>)}
        </ul>
      )}
    </Card>
  );
}

/**
 * The next 24 hours in a strip as wide as the screen's content, which scrolls sideways: «Сейчас»,
 * then the hours, with a curve of the temperature over the cells.
 */
function HoursStrip({ forecast }: { forecast: Forecast }) {
  const t = useT();
  const cells = stripCells(forecast, t.weather.now);
  const curve = temperatureCurve(cells.map((cell) => cell.temperature));
  const now = curve?.points[0];
  return (
    <section className="card strip-card" style={{ "--i": 1 } as CSSProperties}>
      <h2 className="card__title">{t.weather.hours}</h2>
      <div className="strip" role="region" tabIndex={0} aria-label={t.weather.stripLabel}>
        {curve && (
          <svg
            className="strip__curve"
            width={cells.length * CELL_WIDTH}
            height={CURVE_HEIGHT}
            viewBox={`0 0 ${cells.length * CELL_WIDTH} ${CURVE_HEIGHT}`}
            role="img"
            aria-label={t.weather.chart(formatTemp(curve.low), formatTemp(curve.high))}
          >
            <path className="strip__area" d={curve.area} />
            <path className="strip__line" d={curve.line} />
            {now && <circle className="strip__dot" cx={now[0]} cy={now[1]} r="3.5" />}
          </svg>
        )}
        <ul className="strip__cells">
          {cells.map((cell, index) => {
            const temperature = formatTemp(cell.temperature);
            const chance = shownChance(cell.chance);
            return (
              <li
                // Two hours may share a label on the night the clocks go back: the place is the key.
                key={index}
                className={index === 0 ? "strip__cell strip__cell--now" : "strip__cell"}
                aria-label={t.weather.hourLabel(cell.time, cell.description, temperature, chance)}
              >
                <span className="strip__time">{cell.time}</span>
                <span className="strip__icon" aria-hidden>{asEmoji(cell.emoji)}</span>
                <span className="strip__temp">{temperature}</span>
                <span className="strip__chance" aria-hidden>{t.weather.chance(chance)}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

/**
 * Seven days in fixed columns: the day and its chance, the icon, the lowest temperature, the range on
 * the week's scale, the highest.
 */
function WeekCard({ days }: { days: ForecastDay[] }) {
  const t = useT();
  const lang = useLang();
  if (days.length === 0) return null;
  const low = Math.min(...days.map((day) => day.tmin));
  const high = Math.max(...days.map((day) => day.tmax));
  return (
    <Card title={t.weather.days} index={2}>
      <ul className="week">
        {days.map((day, index) => {
          const chance = shownChance(day.precip_chance);
          const bar = rangeBar(day.tmin, day.tmax, low, high);
          const name = weekDayName(index, day.date, lang, t.calendar.words);
          return (
            <li
              key={day.date}
              className="week__day"
              aria-label={t.weather.dayLabel(name, day.description, formatTemp(day.tmin), formatTemp(day.tmax), chance)}
            >
              <span className="week__when">
                <span className="week__name">{weekDayLabel(index, day.date, lang, t.calendar.words)}</span>
                {chance !== null && <span className="week__chance" aria-hidden>{t.weather.chance(chance)}</span>}
              </span>
              <span className="week__icon" aria-hidden>{asEmoji(day.emoji)}</span>
              <span className="week__temp week__temp--low">{formatTemp(day.tmin)}</span>
              <span className="week__bar" aria-hidden>
                <span className="week__range" style={{ "--from": bar.from, "--width": bar.width } as CSSProperties} />
              </span>
              <span className="week__temp">{formatTemp(day.tmax)}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Today's sunrise and sunset, or the polar night or day that has neither. */
function Sun({ forecast }: { forecast: Forecast }) {
  const t = useT();
  const { polar, sunrise, sunset } = forecast;
  let text: string | null = null;
  if (polar === "night") text = t.weather.polarNight;
  else if (polar === "day") text = t.weather.polarDay;
  else if (sunrise !== null && sunset !== null) text = t.weather.sun(sunrise, sunset);
  return text === null ? null : <p className="weather-sun" style={{ "--i": 3 } as CSSProperties}>{text}</p>;
}
