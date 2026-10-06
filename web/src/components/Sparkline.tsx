import type { Point } from "../api";

/** Tiny dependency-free sparkline; the Metrics page uses Recharts for full charts. */
export default function Sparkline({ points, className = "h-8 w-full" }: { points: Point[]; className?: string }) {
  if (points.length < 2) return <div className={className} />;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 100;
  const h = 30;
  const xy = values.map((v, i) => [(i / (values.length - 1)) * w, h - 2 - ((v - min) / span) * (h - 4)] as const);
  const line = xy.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `0,${h} ${line} ${w},${h}`;
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={className} aria-hidden>
      <polygon points={area} className="fill-amber-500/10" />
      <polyline points={line} fill="none" className="stroke-amber-500" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <circle cx={lx} cy={ly} r="1.8" className="fill-amber-500" />
    </svg>
  );
}
