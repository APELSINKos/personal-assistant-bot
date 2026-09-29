import type { CSSProperties, ReactNode } from "react";

export function Card({
  title, index = 0, className = "", children,
}: { title?: ReactNode; index?: number; className?: string; children: ReactNode }) {
  return (
    <section className={`card ${className}`.trim()} style={{ "--i": index } as CSSProperties}>
      {title !== undefined && <h2 className="card__title">{title}</h2>}
      {children}
    </section>
  );
}
