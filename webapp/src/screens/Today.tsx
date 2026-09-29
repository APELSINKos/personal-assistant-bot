import type { CSSProperties } from "react";
import { Link } from "wouter";
import { useSetMark, useToday } from "../api/queries";
import type { Rate, Weather } from "../api/types";
import { Card } from "../components/Card";
import { HabitDots, HabitToggle, nextMark } from "../components/HabitBits";
import { PullToRefresh } from "../components/PullToRefresh";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT, type Lang } from "../i18n";
import { bigDate, formatNumber, formatTemp } from "../lib/format";

function WeatherCard({ weather }: { weather: Weather | null }) {
  const t = useT();
  if (!weather) {
    return (
      <Card index={0}>
        <p className="muted">{t.today.weatherUnavailable}</p>
      </Card>
    );
  }
  return (
    <Card title={weather.city} index={0}>
      <div className="row">
        <span className="temp">{formatTemp(weather.temperature)}</span>
        <span className="weather__desc">
          {weather.emoji} {weather.description}
          <br />
          <span className="muted">
            {formatTemp(weather.tmin).replace("°", "")}…{formatTemp(weather.tmax)}
          </span>
        </span>
      </div>
      {weather.tips[0] && <p className="tip">{weather.tips[0]}</p>}
    </Card>
  );
}

function RateLine({ emoji, code, rate, lang }: { emoji: string; code: string; rate: Rate; lang: Lang }) {
  const change = Math.round(rate.change * 100) / 100;
  const arrow = change > 0 ? "▲" : change < 0 ? "▼" : "•";
  return (
    <div className="row">
      <span>
        {emoji} {code} {formatNumber(rate.value, lang)} ₽
      </span>
      <span className="muted">
        {arrow} {formatNumber(Math.abs(change), lang)}
      </span>
    </div>
  );
}

export function TodayScreen() {
  const t = useT();
  const lang = useLang();
  const today = useToday();
  const setMark = useSetMark();

  if (today.isPending) return <Loader />;
  if (today.isError) return <ErrorState onRetry={() => void today.refetch()} />;

  const data = today.data;
  const date = bigDate(data.date, lang);
  const habits = data.habits.items;
  const done = habits.filter((habit) => habit.done_today === true).length;

  return (
    <PullToRefresh onRefresh={() => today.refetch()}>
      <header className="big-date">
        <span className="big-date__day">{date.day}</span>
        <span className="big-date__meta">
          {date.weekday}
          <br />
          {date.month} {date.year}
        </span>
      </header>

      <WeatherCard weather={data.weather} />

      <Card title={t.today.plans} index={1}>
        {data.reminders_today.length === 0 ? (
          <p className="muted">{t.today.freeDay}</p>
        ) : (
          <ul className="list">
            {data.reminders_today.map((reminder) => (
              <li key={reminder.id}>
                <span className="time">{reminder.time}</span>
                {reminder.text}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={t.today.habits(done, habits.length)} index={2}>
        {habits.length === 0 ? (
          <p className="muted">{t.today.noHabits}</p>
        ) : (
          habits.map((habit) => (
            <div key={habit.id} className="habit">
              <div>
                <div className="habit__name">{habit.name}</div>
                {habit.streak > 0 && <div className="accent">🔥 {t.habits.streak(habit.streak)}</div>}
              </div>
              <HabitToggle
                habit={habit}
                onToggle={() =>
                  setMark.mutate({ id: habit.id, day: data.date, done: nextMark(habit.done_today) })
                }
              />
              <HabitDots days={habit.last_days} />
            </div>
          ))
        )}
        {data.best_streak && (
          <p className="tip accent">{t.today.bestStreak(data.best_streak.name, data.best_streak.days)}</p>
        )}
      </Card>

      {data.rates && (
        <Card index={3}>
          <div className="rates">
            <RateLine emoji="💵" code="USD" rate={data.rates.usd} lang={lang} />
            <RateLine emoji="💶" code="EUR" rate={data.rates.eur} lang={lang} />
          </div>
        </Card>
      )}

      <Link href="/notes" className="card card--link" style={{ "--i": 4 } as CSSProperties}>
        <span>📝 {t.today.notes(data.notes_count)}</span>
        <span aria-hidden>›</span>
      </Link>
    </PullToRefresh>
  );
}
