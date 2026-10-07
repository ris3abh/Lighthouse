import { useRef } from "react";
import type { Point } from "../api";
import { useInView, useReducedMotion } from "../lib/motion";
import { cx } from "./ui";

/** Tiny dependency-free sparkline that fades and draws in (left to right) when it scrolls into view. */
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
    <div className={cx("relative", className)}>
      <svg ref={ref} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="size-full overflow-visible" aria-hidden>
        {/* A clip that widens from the left reveals the line as if it were drawn. */}
        <g className="transition-[clip-path,opacity] duration-[400ms] ease-out" style={{ clipPath: on ? "inset(-10% -10% -10% -2%)" : "inset(-10% 100% -10% -2%)", opacity: on ? 1 : 0 }}>
          <polygon points={area} className="fill-ink/[0.06]" />
          <polyline points={line} fill="none" className="stroke-ink" strokeWidth="1.25" vectorEffect="non-scaling-stroke" />
        </g>
      </svg>
      {/* The endpoint as a real square (an SVG circle would stretch with the chart). */}
      <span
        aria-hidden
        className="absolute size-1.5 -translate-x-1/2 -translate-y-1/2 bg-ink transition-opacity delay-300 duration-200"
        style={{ left: `${(lx / w) * 100}%`, top: `${(ly / h) * 100}%`, opacity: on ? 1 : 0 }}
      />
    </div>
  );
}
