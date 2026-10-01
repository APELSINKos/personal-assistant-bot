import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "wouter";
import { useCities, useHealth, useMe, useSchedule, useSetCity, useUpdateMe } from "../api/queries";
import type { City } from "../api/types";
import { Card } from "../components/Card";
import { ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { useDebounced } from "../lib/useDebounced";
import { openLink } from "../telegram";

export const REPO_URL = "https://github.com/APELSINKos/personal-assistant-bot";

function cityLabel(city: City): string {
  const parts: string[] = [];
  for (const part of [city.name, city.admin, city.country]) {
    if (part && !parts.includes(part)) parts.push(part);
  }
  return parts.join(", ");
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
  const me = useMe();
  const health = useHealth();
  const schedule = useSchedule();
  const update = useUpdateMe();
  const setCity = useSetCity();
  const [query, setQuery] = useState("");
  const search = useDebounced(query, 300);
  const cities = useCities(search);

  if (me.isPending) return <Loader />;
  if (me.isError) return <ErrorState onRetry={() => void me.refetch()} />;
  const profile = me.data;
  const source = schedule.data?.source;

  const chooseCity = (city: City) =>
    setCity.mutate(city, {
      onSuccess: () => {
        setQuery("");
        toast({ kind: "success", text: t.common.saved });
      },
    });

  return (
    <>
      <h1 className="screen__title">{t.tabs.more}</h1>

      <Card title={t.more.city} index={0}>
        <p>{profile.city.name}</p>
        <label className="field">
          <span className="field__label">{t.more.searchCity}</span>
          <input
            className="input"
            type="search"
            maxLength={50}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        {/* Both the live query and the debounced one must be long enough — otherwise, right
            after picking a city (which clears `query`), the stale suggestions would linger
            for up to the debounce delay while `search` catches up. */}
        {query.trim().length >= 2 && search.trim().length >= 2 && cities.isError && !cities.data && (
          <p className="muted">{t.errors.upstream_unavailable}</p>
        )}
        {query.trim().length >= 2 && search.trim().length >= 2 && cities.data && (
          cities.data.length === 0 ? (
            <p className="muted">{t.more.noCities}</p>
          ) : (
            <div className="results">
              {cities.data.map((city) => (
                <button
                  type="button"
                  key={`${city.lat},${city.lon}`}
                  className="result"
                  onClick={() => chooseCity(city)}
                >
                  {cityLabel(city)}
                </button>
              ))}
            </div>
          )
        )}
      </Card>

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

      <Card title={t.more.about} index={4}>
        {health.data && <p className="muted">{t.more.version(health.data.version)}</p>}
        <button type="button" className="button" onClick={() => openLink(REPO_URL)}>
          {t.more.source}
        </button>
      </Card>
    </>
  );
}
