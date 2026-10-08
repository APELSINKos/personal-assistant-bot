import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "wouter";
import {
  CITY_QUERY_MAX, searchable, useAddCity, useCities, useDeleteCity, useHealth, useMe, useSchedule, useSetCity,
  useUpdateMe, useWeatherCities,
} from "../api/queries";
import type { City, WeatherCity } from "../api/types";
import { Card } from "../components/Card";
import { Credit } from "../components/Credit";
import { SearchStatus } from "../components/SearchStatus";
import { ErrorState, Loader } from "../components/States";
import { SwipeRow } from "../components/SwipeRow";
import { useTextLimit } from "../components/TextLimit";
import { toast } from "../components/toastStore";
import { useLang, useT } from "../i18n";
import { CURRENCY_CODES, currencyName, currencySign } from "../lib/money";
import { useDebounced } from "../lib/useDebounced";
import { openLink } from "../telegram";

export const REPO_URL = "https://github.com/APELSINKos/personal-assistant-bot";

/** The extra cities of the weather, the home one aside (LIMITS.cities on the server). */
const MAX_EXTRA_CITIES = 4;

/** A place's names, each once: a city may be its own region, as Moscow is. */
function placeNames(city: City): string[] {
  const parts: string[] = [];
  for (const part of [city.name, city.admin, city.country]) {
    if (part && !parts.includes(part)) parts.push(part);
  }
  return parts;
}

/** What the search does with a found city: puts it in place of the home one, or adds it. */
type CityMode = "home" | "add";

/**
 * The city search of a mode, open while its button says so. Only the query is its own: the
 * requests belong to the card, so a city saved after the search closed is still told.
 */
function CitySearch({
  id, mode, busy, onChoose,
}: { id: string; mode: CityMode; busy: boolean; onChoose: (city: City) => void }) {
  const t = useT();
  const field = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const search = useDebounced(query, 300);
  const results = useCities(search);
  const queryLimit = useTextLimit(query.trim(), CITY_QUERY_MAX);
  // Both the live query and the debounced one: right after a change, the suggestions of the
  // query before it must not linger for the debounce delay.
  const searching = searchable(query, CITY_QUERY_MAX) && searchable(search, CITY_QUERY_MAX);
  const found = searching && results.data ? results.data.length : 0;

  // The field takes the focus, and a phone its keyboard, when the search opens or changes mode.
  useEffect(() => {
    field.current?.focus();
  }, [mode]);

  return (
    <div className="city-search" id={id}>
      <label className="field">
        <span className="field__label">{mode === "home" ? t.more.newHome : t.more.cityToAdd}</span>
        <input
          ref={field}
          className="input"
          type="search"
          value={query}
          {...queryLimit.field}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {queryLimit.hint}
      {/* While a city saves, the results are off but not `disabled`: a disabled button drops the
          focus, and a keyboard would start again from the top of the screen. */}
      {searching && results.data && results.data.length > 0 && (
        <div className="results">
          {results.data.map((city) => (
            <button
              type="button"
              key={`${city.lat},${city.lon}`}
              className="result"
              aria-disabled={busy || undefined}
              onClick={() => onChoose(city)}
            >
              {placeNames(city).join(", ")}
            </button>
          ))}
        </div>
      )}
      <SearchStatus count={found > 0 ? t.more.citiesFound(found) : null}>
        {searching && results.isError && !results.data && <p className="muted">{t.errors.upstream_unavailable}</p>}
        {searching && results.data?.length === 0 && <p className="muted">{t.more.noCities}</p>}
      </SearchStatus>
    </div>
  );
}

/**
 * The cities of the weather: the home one, whose clock everything keeps, and up to four more,
 * each deleted by a swipe without a question (it is easy to add again). The search is there only
 * when a button asks for it, and the same button hides it again: «Сменить домашний» puts the
 * city found in place of the home one, «Добавить город» adds it to the others. A city saved
 * closes the search, and the focus goes back to the button; one refused leaves it open, for
 * another choice.
 */
function CitiesCard({ home, list, index }: { home: string; list: UseQueryResult<WeatherCity[]>; index: number }) {
  const t = useT();
  const setCity = useSetCity();
  const addCity = useAddCity();
  const remove = useDeleteCity();
  const [mode, setMode] = useState<CityMode | null>(null);
  const searchId = useId();
  const limitId = useId();
  const homeToggle = useRef<HTMLButtonElement>(null);
  const addToggle = useRef<HTMLButtonElement>(null);
  // The search on screen at the last commit, to tell one that has just closed.
  const shown = useRef<CityMode | null>(null);
  const extra = list.data ?? [];
  const full = extra.length >= MAX_EXTRA_CITIES;
  const busy = setCity.isPending || addCity.isPending;
  if (mode === "add" && full) {
    // The list filled up meanwhile (a city added in the bot): there is nothing more to add.
    setMode(null);
  }

  // A search that closes by itself (a city saved, the list full) takes the focus with it, as does
  // «Добавить город» turning off under it. The focus goes back to the button that opened the
  // search, or to «Сменить домашний» when «Добавить город» is off, not to the top of the screen.
  // A layout effect: it runs before the browser drops the focus of a button just turned off.
  useLayoutEffect(() => {
    const closed = shown.current;
    shown.current = mode;
    const focused = document.activeElement;
    const lost = closed !== null && mode === null && (focused === null || focused === document.body);
    if (lost || (full && focused === addToggle.current)) {
      (closed === "add" && !full ? addToggle : homeToggle).current?.focus();
    }
  }, [mode, full]);

  const toggle = (pressed: CityMode) => setMode(mode === pressed ? null : pressed);
  const choose = (city: City) => {
    // The results stay focusable while a city saves: a second choice in the meantime is not taken.
    if (busy) return;
    const saved = {
      onSuccess: () => {
        toast({ kind: "success", text: t.common.saved });
        setMode(null);
      },
    };
    if (mode === "home") setCity.mutate(city, saved);
    else addCity.mutate(city, saved);
  };

  return (
    <Card title={t.more.cities} index={index}>
      <p className="city-home">
        <span className="city-home__name">🏠 {home}</span>
        <span className="muted city-home__hint">{t.more.homeHint}</span>
      </p>
      {list.isLoadingError && <ErrorState onRetry={() => void list.refetch()} />}
      {extra.length > 0 && (
        <ul className="city-list">
          {extra.map((city) => {
            const area = placeNames(city).slice(1).join(", ");
            return (
              <li key={city.id}>
                <SwipeRow
                  onDelete={() => remove.mutate(city.id)}
                  deleteLabel={t.more.deleteCity(city.name)}
                  question={t.more.confirmDeleteCity(city.name)}
                >
                  <span className="city-list__name">{city.name}</span>
                  {area && <span className="muted city-list__area">{area}</span>}
                </SwipeRow>
              </li>
            );
          })}
        </ul>
      )}
      <div className="city-actions">
        <button
          ref={homeToggle}
          type="button"
          className="button"
          aria-expanded={mode === "home"}
          aria-controls={mode === null ? undefined : searchId}
          onClick={() => toggle("home")}
        >
          {t.more.changeHome}
        </button>
        <button
          ref={addToggle}
          type="button"
          className="button"
          aria-expanded={mode === "add"}
          aria-controls={mode === null ? undefined : searchId}
          aria-describedby={full ? limitId : undefined}
          disabled={full}
          onClick={() => toggle("add")}
        >
          {t.more.addCity}
        </button>
      </div>
      {full && <p className="muted field__note" id={limitId}>{t.more.citiesLimit}</p>}
      {mode !== null && (
        <CitySearch id={searchId} mode={mode} busy={busy} onChoose={choose} />
      )}
    </Card>
  );
}

const COMPLETE_TIME = /^\d{2}:\d{2}$/;

/**
 * A desktop time field reports every keystroke as a complete time (00:00 → 09:00 → 09:03 →
 * 09:30), so the field keeps its own value and saves it when left, or once typing has paused.
 */
function MorningTime({ saved, disabled, onSave }: { saved: string; disabled: boolean; onSave: (time: string) => void }) {
  const t = useT();
  const [draft, setDraft] = useState(saved);
  const [shown, setShown] = useState(saved);
  if (saved !== shown) {
    // The stored time changed (this field's own save, a rollback, the bot): show it.
    setShown(saved);
    setDraft(saved);
  }
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const save = (value: string) => {
    clearTimeout(timer.current);
    if (COMPLETE_TIME.test(value) && value !== saved) onSave(value);
  };
  return (
    <label className="field">
      <span className="field__label">{t.more.morningTime}</span>
      <input
        className="input"
        type="time"
        disabled={disabled}
        value={draft}
        onChange={(event) => {
          const value = event.target.value;
          setDraft(value);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => save(value), 800);
        }}
        onBlur={() => {
          save(draft);
          if (!COMPLETE_TIME.test(draft)) setDraft(saved);
        }}
      />
    </label>
  );
}

export function MoreScreen() {
  const t = useT();
  const lang = useLang();
  const me = useMe();
  // Asked for with /me rather than after it: the card of the cities needs both.
  const cities = useWeatherCities();
  const health = useHealth();
  const schedule = useSchedule();
  const update = useUpdateMe();

  if (me.isPending) return <Loader />;
  // A failed refresh keeps the settings on screen: only a first load that failed is an error.
  if (me.isLoadingError) return <ErrorState onRetry={() => void me.refetch()} />;
  const profile = me.data;
  const source = schedule.data?.source;

  return (
    <>
      <h1 className="screen__title">{t.tabs.more}</h1>

      <CitiesCard home={profile.city.name} list={cities} index={0} />

      <Link href="/more/schedule" className="card card--link" style={{ "--i": 1 } as CSSProperties}>
        <span>
          🎓 {t.schedule.entry}{" "}
          {schedule.data && (
            <span className="muted card__sub">
              {source ? (source.title ?? t.schedule.untitled) : t.schedule.notConnected}
            </span>
          )}
        </span>
        <span aria-hidden>›</span>
      </Link>

      <Card index={2}>
        <label className="switch-row row field">
          <span>{t.more.morning}</span>
          <input
            type="checkbox"
            role="switch"
            className="switch"
            checked={profile.morning.enabled}
            onChange={(event) => update.mutate({ morning_enabled: event.target.checked })}
          />
        </label>
        <MorningTime
          saved={profile.morning.time}
          disabled={!profile.morning.enabled}
          onSave={(time) => update.mutate({ morning_time: time })}
        />
      </Card>

      <Card title={t.more.language} index={3}>
        <div className="segmented" role="group" aria-label={t.more.language}>
          {(["auto", "ru", "en"] as const).map((option) => (
            <button
              type="button"
              key={option}
              className="segmented__option"
              aria-pressed={profile.language_setting === option}
              onClick={() => update.mutate({ language: option })}
            >
              {option === "auto" ? t.more.auto : t.more.languageNames[option]}
            </button>
          ))}
        </div>
      </Card>

      <Card title={t.more.currency} index={4}>
        <select
          className="input"
          aria-label={t.more.currency}
          value={profile.currency}
          onChange={(event) => update.mutate({ currency: event.target.value })}
        >
          {CURRENCY_CODES.map((code) => (
            <option key={code} value={code}>{`${currencySign(code)} ${code} — ${currencyName(code, lang)}`}</option>
          ))}
        </select>
        <p className="muted field__note">{t.more.currencyHint}</p>
      </Card>

      {/* The licence of the weather and of the city names (CC BY 4.0) asks for their sources. */}
      <Card title={t.more.data} index={5}>
        <Credit text={t.more.credits} className="credit--card" />
      </Card>

      <Card title={t.more.about} index={6}>
        {health.data && <p className="muted">{t.more.version(health.data.version)}</p>}
        <button type="button" className="button" onClick={() => openLink(REPO_URL)}>
          {t.more.source}
        </button>
      </Card>
    </>
  );
}
