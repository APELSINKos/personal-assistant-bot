import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "wouter";
import { useSetMark, useToday } from "../api/queries";
import type { ClassesWeather, ForecastDay, PinnedNote, Rate, TodayLesson, TodayMoney, Weather } from "../api/types";
import { Card } from "../components/Card";
import { HabitDots, HabitToggle, nextMark } from "../components/HabitBits";
import { BudgetBar } from "../components/MoneyCharts";
import { NoteProgress } from "../components/NoteBits";
import { PullToRefresh } from "../components/PullToRefresh";
import { ErrorState, Loader } from "../components/States";
import { useLang, useT, type Lang } from "../i18n";
import { bigDate, capitalize, formatNumber, formatRange, formatTemp, lessonMeta, shownChance } from "../lib/format";
import { budgetText, formatAmount, monthName } from "../lib/money";
import { asEmoji, classesLine, nextClassesChange } from "../lib/weather";

/**
 * A line of text with a weather icon in it: the icon in a span of its own, which the light theme
 * draws with an edge (weather.css). A line without the icon stays as it is.
 */
function withIcon(text: string, icon: string): ReactNode {
  const at = icon === "" ? -1 : text.indexOf(icon);
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <span className="weather-today__icon">{icon}</span>
      {text.slice(at + icon.length)}
    </>
  );
}

/**
 * The weather now, and from 17:00 tomorrow's; a tap opens the «Погода» screen — also without the
 * weather, as that screen has its own «Повторить».
 */
function WeatherCard({ weather, tomorrow }: { weather: Weather | null; tomorrow: ForecastDay | null }) {
  const t = useT();
  const style = { "--i": 0 } as CSSProperties;
  if (!weather) {
    return (
      <Link href="/weather" className="card card--link" style={style}>
        <span className="muted">{t.today.weatherUnavailable}</span>
        <span aria-hidden>›</span>
      </Link>
    );
  }
  const icon = tomorrow ? asEmoji(tomorrow.emoji) : "";
  const later = tomorrow && t.today.withChance(
    t.today.tomorrow(icon, formatRange(tomorrow.tmin, tomorrow.tmax)),
    shownChance(tomorrow.precip_chance),
  );
  return (
    <Link href="/weather" className="card weather-today" style={style}>
      <span className="card__title weather-today__title">
        <span>{weather.city}</span>
        <span aria-hidden>›</span>
      </span>
      <span className="row">
        <span className="temp">{formatTemp(weather.temperature)}</span>
        <span className="weather__desc">
          <span><span className="weather-today__icon">{asEmoji(weather.emoji)}</span> {weather.description}</span>
          {weather.feels_like !== null && (
            <span className="muted">{t.today.feelsLike(formatTemp(weather.feels_like))}</span>
          )}
          <span className="muted">{formatRange(weather.tmin, weather.tmax)}</span>
        </span>
      </span>
      {weather.tips[0] && <span className="tip">{weather.tips[0]}</span>}
      {later && <span className="muted weather-today__tomorrow">{withIcon(later, icon)}</span>}
    </Link>
  );
}

/** Whether every lesson of the day has already ended (read at render time). */
function lessonsOver(lessons: TodayLesson[], now: number = Date.now()): boolean {
  return lessons.every((lesson) => now >= Date.parse(lesson.ends_at));
}

// A longer delay makes setTimeout fire at once instead.
const MAX_TIMEOUT = 2 ** 31 - 1;

function LessonsCard({
  lessons, weekLabel, classesWeather, index,
}: { lessons: TodayLesson[]; weekLabel: string | null; classesWeather: ClassesWeather | null; index: number }) {
  const t = useT();
  const [tick, setTick] = useState(0);
  // The card is decided at render time — «На пары» until the first lesson begins, «Пары закончились»
  // once the last one has ended — and while the screen stays open nothing else re-renders it at
  // those moments. So one timer, up to the next of them, does. It is cleared on unmount and re-armed
  // when the lessons change, after it fires (`tick` re-runs this effect) and when it fires early.
  useEffect(() => {
    const now = Date.now();
    const next = nextClassesChange(lessons, now);
    if (next === null) return;
    const timer = setTimeout(() => setTick((count) => count + 1), Math.min(next - now, MAX_TIMEOUT));
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
  const way = classesLine(classesWeather, lessons, t);
  return (
    <Card title={weekLabel ? `${t.today.lessons} · ${weekLabel}` : t.today.lessons} index={index}>
      {lessonsOver(lessons) ? (
        <p className="muted">{t.today.lessonsOver}</p>
      ) : (
        <>
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
          {way && <p className="tip">{way}</p>}
        </>
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

/**
 * The notes: the first three pinned ones, each opening its note, and the way to all of them; with
 * nothing pinned, only how many there are.
 */
function NotesCard({ count, pinned, index }: { count: number; pinned: PinnedNote[]; index: number }) {
  const t = useT();
  const style = { "--i": index } as CSSProperties;
  if (pinned.length === 0) {
    return (
      <Link href="/notes" className="card card--link" style={style}>
        <span>📝 {t.today.notes(count)}</span>
        <span aria-hidden>›</span>
      </Link>
    );
  }
  return (
    <section className="card notes-today" style={style}>
      <h2 className="card__title">{t.tabs.notes}</h2>
      <ul className="notes-today__list">
        {pinned.map((note) => (
          <li key={note.id}>
            {/* Plain text, addresses too: a tap anywhere on the line opens the note. */}
            <Link href={`/notes/${note.id}`} className="notes-today__note">
              <span className="notes-today__text">
                <span aria-hidden>📌 </span>
                {note.text}
              </span>
              {/* The space parts the text from the progress in the link's spoken name. */}
              {note.total > 0 && <> <NoteProgress done={note.done} total={note.total} /></>}
            </Link>
          </li>
        ))}
      </ul>
      <Link href="/notes" className="notes-today__all">
        <span>{t.today.allNotes(count)}</span>
        <span aria-hidden>›</span>
      </Link>
    </section>
  );
}

/** Spent today and the month's budget; a tap opens the «Деньги» tab. */
function MoneyCard({ money, date, index }: { money: TodayMoney; date: string; index: number }) {
  const t = useT();
  const lang = useLang();
  const month = `${capitalize(monthName(date, lang))}: ${formatAmount(money.spent, money.currency, lang)}`;
  const budget = money.budget !== null && money.left !== null
    ? budgetText(money.budget, money.left, money.per_day, money.currency, lang, t)
    : null;
  return (
    <Link href="/money" className="card money-today" style={{ "--i": index } as CSSProperties}>
      <span className="card__title">{t.tabs.money}</span>
      <span className="row">
        <span>{t.calendar.words.today}</span>
        <span className="money-today__amount">{formatAmount(money.today, money.currency, lang)}</span>
      </span>
      {money.budget !== null && <BudgetBar spent={money.spent} budget={money.budget} />}
      <span className="muted money-today__month">{budget === null ? month : `${month} ${budget}`}</span>
    </Link>
  );
}

export function TodayScreen() {
  const t = useT();
  const lang = useLang();
  const today = useToday();
  const setMark = useSetMark();

  if (today.isPending) return <Loader />;
  // A failed refresh keeps the day on screen: only a first load that failed is an error.
  if (today.isLoadingError) return <ErrorState onRetry={() => void today.refetch()} />;

  const data = today.data;
  const date = bigDate(data.date, lang);
  const habits = data.habits.items;
  const done = habits.filter((habit) => habit.done_today === true).length;
  // No lessons today (or no timetable at all) means no card; the cards below shift up a step.
  const shift = data.lessons.length > 0 ? 1 : 0;
  // Neither entries this month nor a budget: no card, and the ones below move up a step.
  const money = data.money && (data.money.count > 0 || data.money.budget !== null) ? data.money : null;
  const moneyShift = money ? 1 : 0;

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

      <WeatherCard weather={data.weather} tomorrow={data.tomorrow} />

      {shift > 0 && (
        <LessonsCard
          lessons={data.lessons}
          weekLabel={data.week_label}
          classesWeather={data.classes_weather}
          index={1}
        />
      )}

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
                {habit.streak > 0 && <div className="accent">🔥 {t.habits.streakIn(habit.streak, habit.streak_unit)}</div>}
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
          <p className="tip accent">{t.today.bestStreak(data.best_streak.name, data.best_streak.count, data.best_streak.unit)}</p>
        )}
      </Card>

      {money && <MoneyCard money={money} date={data.date} index={3 + shift} />}

      {data.rates && (
        <Card index={3 + shift + moneyShift}>
          <div className="rates">
            <RateLine emoji="💵" code="USD" rate={data.rates.usd} lang={lang} />
            <RateLine emoji="💶" code="EUR" rate={data.rates.eur} lang={lang} />
          </div>
        </Card>
      )}

      <NotesCard count={data.notes_count} pinned={data.pinned_notes} index={4 + shift + moneyShift} />
    </PullToRefresh>
  );
}
