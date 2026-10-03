import type { RatePoint } from "../api/types";
import type { Lang } from "../i18n";
import { dayMonth } from "../lib/format";
import { budgetUse, formatRate, type RingPart } from "../lib/money";

/** How much of a budget is spent. The words next to it say the same, so it is hidden from readers. */
export function BudgetBar({ spent, budget }: { spent: number; budget: number }) {
  const { percent, tone } = budgetUse(spent, budget);
  return (
    <div className={`budget-bar budget-bar--${tone}`} aria-hidden>
      <div className="budget-bar__fill" style={{ width: `${percent}%` }} />
    </div>
  );
}

const RADIUS = 48;
const CIRCLE = 2 * Math.PI * RADIUS;

/** The month's expenses as a ring, clockwise from the top, with the number of entries inside. */
export function Ring({
  parts, label, count, caption,
}: { parts: RingPart[]; label: string; count: string; caption: string }) {
  const total = parts.reduce((sum, part) => sum + part.amount, 0);
  const gap = parts.length > 1 ? 1.5 : 0; // between two slices, along the circle
  const before = parts.map((_, index) => parts.slice(0, index).reduce((sum, part) => sum + part.amount, 0));
  return (
    <svg className="ring" viewBox="0 0 120 120" role="img" aria-label={label}>
      <g transform="rotate(-90 60 60)">
        {parts.map((part, index) => {
          const length = Math.max((part.amount / total) * CIRCLE - gap, 0.5);
          return (
            <circle
              key={part.id ?? "rest"}
              cx="60"
              cy="60"
              r={RADIUS}
              fill="none"
              stroke={part.color}
              strokeWidth="16"
              strokeDasharray={`${length} ${CIRCLE - length}`}
              strokeDashoffset={-((before[index] ?? 0) / total) * CIRCLE}
            />
          );
        })}
      </g>
      <text x="60" y="61" textAnchor="middle" className="ring__count">{count}</text>
      <text x="60" y="77" textAnchor="middle" className="ring__caption">{caption}</text>
    </svg>
  );
}

/** A month's spending by day: a bar a day, today's in the accent colour, none for the days ahead. */
export function DayBars({ days, today, label }: { days: (number | null)[]; today: number; label: string }) {
  const most = Math.max(1, ...days.map((value) => value ?? 0));
  return (
    <div className="day-bars">
      <svg
        className="day-bars__chart"
        viewBox={`0 0 ${days.length * 10} 60`}
        preserveAspectRatio="none"
        role="img"
        aria-label={label}
      >
        {days.map((value, index) => {
          if (value === null) return null;
          const height = value > 0 ? Math.max(2, (value / most) * 60) : 1;
          const tone = index + 1 === today ? " day-bars__bar--today" : value > 0 ? "" : " day-bars__bar--zero";
          return (
            <rect key={index} className={`day-bars__bar${tone}`} x={index * 10 + 2} y={60 - height} width="6" height={height} />
          );
        })}
      </svg>
      <div className="day-bars__axis" aria-hidden>
        {[1, 10, 20, days.length].map((day) => (
          <span key={day} style={{ left: `${((day - 0.5) / days.length) * 100}%` }}>{day}</span>
        ))}
      </div>
    </div>
  );
}

/** A rate's last days as a small line in a list's row; the row's numbers say the rest. */
export function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="sparkline" aria-hidden />;
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const line = values
    .map((value, index) => `${((index / (values.length - 1)) * 60).toFixed(1)},${(22 - ((value - low) / span) * 20).toFixed(1)}`)
    .join(" ");
  return (
    <svg className="sparkline" viewBox="0 0 60 24" aria-hidden>
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** A rate over its days: the line, the highest and the lowest value beside it, the first and the last day under it. */
export function LineChart({ points, label, lang }: { points: RatePoint[]; label: string; lang: Lang }) {
  const values = points.map((point) => point.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const line = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 300;
      return `${x.toFixed(1)},${(112 - ((point.value - low) / span) * 104).toFixed(1)}`;
    })
    .join(" ");
  return (
    <figure className="line-chart">
      <svg className="line-chart__plot" viewBox="0 0 300 120" preserveAspectRatio="none" role="img" aria-label={label}>
        <polyline
          points={line}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="line-chart__scale" aria-hidden>
        <span>{formatRate(high, lang)}</span>
        <span>{formatRate(low, lang)}</span>
      </div>
      <div className="line-chart__days" aria-hidden>
        <span>{dayMonth(points[0]?.day ?? "", lang)}</span>
        <span>{dayMonth(points.at(-1)?.day ?? "", lang)}</span>
      </div>
    </figure>
  );
}
