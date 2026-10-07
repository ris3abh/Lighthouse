import { useRef } from "react";
import type { Point } from "../api";
import { cx } from "./ui";
import { useInView, useReducedMotion } from "../lib/motion";

/** Tiny dependency-free sparkline that fades and draws in when it scrolls into view. */
export default function Sparkline({ points, className = "h-10 w-full" }: { points: Point[]; className?: string }) {
  const ref = useRef<SVGSVGElement>(null);
  const seen = useInView(ref);
  const reduced = useReducedMotion();
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
  const on = seen || reduced;
  return (
    <svg ref={ref} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cx(className, "overflow-visible")} aria-hidden>
      <polygon points={area} className="fill-ink/[0.06] transition-opacity delay-200 duration-300" style={{ opacity: on ? 1 : 0 }} />
      <polyline
        points={line}
        fill="none"
        className="stroke-ink transition-[stroke-dashoffset] duration-[400ms] ease-out"
        strokeWidth="1.25"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        strokeDasharray="1"
        style={{ strokeDashoffset: on ? 0 : 1 }}
      />
      <circle cx={lx} cy={ly} r="1.6" className="fill-ink transition-opacity delay-300 duration-200" style={{ opacity: on ? 1 : 0 }} />
    </svg>
  );
}
