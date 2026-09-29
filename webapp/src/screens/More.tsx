import { useState } from "react";
import { useCities, useHealth, useMe, useSetCity, useUpdateMe } from "../api/queries";
import type { City } from "../api/types";
import { Card } from "../components/Card";
import { ErrorState, Loader } from "../components/States";
import { toast } from "../components/toastStore";
import { useT } from "../i18n";
import { useDebounced } from "../lib/useDebounced";
import { openLink } from "../telegram";

export const REPO_URL = "https://github.com/APELSINKos/personal-assistant-bot";
const LANGUAGE_NAMES = { ru: "Русский", en: "English" } as const;

function cityLabel(city: City): string {
  const parts: string[] = [];
  for (const part of [city.name, city.admin, city.country]) {
    if (part && !parts.includes(part)) parts.push(part);
  }
  return parts.join(", ");
}

export function MoreScreen() {
  const t = useT();
  const me = useMe();
  const health = useHealth();
  const update = useUpdateMe();
  const setCity = useSetCity();
  const [query, setQuery] = useState("");
  const search = useDebounced(query, 300);
  const cities = useCities(search);

  if (me.isPending) return <Loader />;
  if (me.isError) return <ErrorState onRetry={() => void me.refetch()} />;
  const profile = me.data;

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
        {search.trim().length >= 2 && cities.data && (
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

      <Card index={1}>
        <label className="row field">
          <span className="card__title">{t.more.morning}</span>
          <input
            type="checkbox"
            role="switch"
            className="switch"
            checked={profile.morning.enabled}
            onChange={(event) => update.mutate({ morning_enabled: event.target.checked })}
          />
        </label>
        <label className="field">
          <span className="field__label">{t.more.morningTime}</span>
          <input
            className="input"
            type="time"
            disabled={!profile.morning.enabled}
            value={profile.morning.time}
            onChange={(event) => {
              if (/^\d{2}:\d{2}$/.test(event.target.value)) update.mutate({ morning_time: event.target.value });
            }}
          />
        </label>
      </Card>

      <Card title={t.more.language} index={2}>
        <div className="segmented" role="group" aria-label={t.more.language}>
          {(["auto", "ru", "en"] as const).map((option) => (
            <button
              type="button"
              key={option}
              className="segmented__option"
              aria-pressed={profile.language_setting === option}
              onClick={() => update.mutate({ language: option })}
            >
              {option === "auto" ? t.more.auto : LANGUAGE_NAMES[option]}
            </button>
          ))}
        </div>
      </Card>

      <Card title={t.more.about} index={3}>
        {health.data && <p className="muted">{t.more.version(health.data.version)}</p>}
        <button type="button" className="button" onClick={() => openLink(REPO_URL)}>
          {t.more.source}
        </button>
      </Card>
    </>
  );
}
