import { budgetUse, type RingPart } from "../lib/money";

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
