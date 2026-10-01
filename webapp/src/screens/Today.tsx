import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "wouter";
import { useSetMark, useToday } from "../api/queries";
import type { Rate, TodayLesson, Weather } from "../api/types";
import { Card } from "../components/Card";
import { HabitDots, HabitToggle, nextMark } from "../components/HabitBits";
import { PullToRefresh } from "../components/PullToRefresh";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT, type Lang } from "../i18n";
import { bigDate, formatNumber, formatTemp, lessonMeta } from "../lib/format";

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

/** Whether every lesson of the day has already ended (read at render time). */
function lessonsOver(lessons: TodayLesson[], now: number = Date.now()): boolean {
  return lessons.every((lesson) => now >= Date.parse(lesson.ends_at));
}

// A longer delay makes setTimeout fire at once instead.
const MAX_TIMEOUT = 2 ** 31 - 1;

function LessonsCard({
  lessons, weekLabel, index,
}: { lessons: TodayLesson[]; weekLabel: string | null; index: number }) {
  const t = useT();
  const [tick, setTick] = useState(0);
  // «Пары закончились» is decided at render time, and while the screen stays open nothing else re-renders
  // the card when the day's last lesson ends. So one timer, up to that moment, does. It is cleared on
  // unmount and re-armed when the lessons change (or after it fires early: `tick` re-runs this effect).
  useEffect(() => {
    const wait = Math.max(...lessons.map((lesson) => Date.parse(lesson.ends_at))) - Date.now();
    if (!(wait > 0)) return;
    const timer = setTimeout(() => setTick((count) => count + 1), Math.min(wait, MAX_TIMEOUT));
    return () => clearTimeout(timer);
  }, [lessons, tick]);
  // The timer runs on uptime, so after the device slept it fires late, and a refetch with the
  // same lessons re-renders nothing: coming back to the app checks again.
  useEffect(() => {
    const recheck = () => {
      if (document.visibilityState === "visible") setTick((count) => count + 1);
    };
    document.addEventListener("visibilitychange", recheck);
    return () => document.removeEventListener("visibilitychange", recheck);
  }, []);
  return (
    <Card title={weekLabel ? `${t.today.lessons} · ${weekLabel}` : t.today.lessons} index={index}>
      {lessonsOver(lessons) ? (
        <p className="muted">{t.today.lessonsOver}</p>
      ) : (
        <ul className="list">
          {lessons.map((lesson, position) => (
            <li key={`${lesson.starts_at}-${position}`} className="lesson">
              <span className="time">{lesson.time}</span>
              <span className="lesson__body">
                <span>{lesson.title}</span>
                <span className="muted lesson__meta">
                  {lessonMeta(lesson.kind, lesson.time, lesson.end, lesson.room)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
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
  // No lessons today (or no timetable at all) means no card; the cards below shift up a step.
  const shift = data.lessons.length > 0 ? 1 : 0;

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

      {shift > 0 && <LessonsCard lessons={data.lessons} weekLabel={data.week_label} index={1} />}

      <Card title={t.today.plans} index={1 + shift}>
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

      <Card title={t.today.habits(done, habits.length)} index={2 + shift}>
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
        <Card index={3 + shift}>
          <div className="rates">
            <RateLine emoji="💵" code="USD" rate={data.rates.usd} lang={lang} />
            <RateLine emoji="💶" code="EUR" rate={data.rates.eur} lang={lang} />
          </div>
        </Card>
      )}

      <Link href="/notes" className="card card--link" style={{ "--i": 4 + shift } as CSSProperties}>
        <span>📝 {t.today.notes(data.notes_count)}</span>
        <span aria-hidden>›</span>
      </Link>
    </PullToRefresh>
  );
}
