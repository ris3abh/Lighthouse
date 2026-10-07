import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Point } from "../api";
import { useReducedMotion } from "../lib/motion";
import { fmt, Segmented } from "./ui";

export type Range = "30d" | "90d" | "1y" | "all";
const DAYS: Record<Range, number> = { "30d": 30, "90d": 90, "1y": 365, all: Infinity };

export function inRange(points: Point[], range: Range) {
  if (range === "all" || !points.length) return points;
  const last = new Date(points[points.length - 1].date + "T00:00").getTime();
  const from = last - DAYS[range] * 86_400_000;
  const out = points.filter((p) => new Date(p.date + "T00:00").getTime() >= from);
  return out.length >= 2 ? out : points.slice(-2);
}

export function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <Segmented
      label="Date range"
      size="sm"
      value={value}
      onChange={onChange}
      options={[
        { value: "30d", label: "30D" },
        { value: "90d", label: "90D" },
        { value: "1y", label: "1Y" },
        { value: "all", label: "All" },
      ]}
    />
  );
}

function compact(v: number) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

/**
 * A line chart that draws itself in left to right, and morphs (doesn't redraw) when the data changes: the chart
 * stays mounted and Recharts interpolates between the old and new points. Hover shows a thin crosshair with the
 * exact value and date in mono type; the nearest point grows. Reduced motion: no animation.
 */
export default function TrendChart({ points, label, height = 260 }: { points: Point[]; label: string; height?: number }) {
  const reduced = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);
  const data = useMemo(() => points.map((p) => ({ date: p.date, value: p.value })), [points]);
  return (
    <div className="text-ink [&_.recharts-active-dot_circle]:animate-[dot-grow_160ms_ease-out]" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 12, right: 16, bottom: 4, left: 0 }}
          onMouseMove={(s) => {
            const i = typeof s?.activeTooltipIndex === "number" ? s.activeTooltipIndex : Number(s?.activeTooltipIndex);
            setHover(Number.isFinite(i) && data[i] ? data[i].value : null);
          }}
          onMouseLeave={() => setHover(null)}
        >
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(d: string) => d.slice(5)}
            tick={{ fontSize: 10.5, fill: "var(--muted)", fontFamily: "var(--font-mono)" }}
            stroke="var(--line)"
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            tickFormatter={(v: number) => compact(v)}
            tick={{ fontSize: 10.5, fill: "var(--muted)", fontFamily: "var(--font-mono)" }}
            stroke="var(--line)"
            tickLine={false}
            axisLine={false}
            width={48}
            domain={["auto", "auto"]}
          />
          {hover !== null && <ReferenceLine y={hover} stroke="var(--ink)" strokeWidth={1} strokeOpacity={0.35} ifOverflow="extendDomain" />}
          <Tooltip
            cursor={{ stroke: "var(--ink)", strokeWidth: 1, strokeOpacity: 0.6 }}
            isAnimationActive={false}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="border border-ink bg-surface px-3 py-2 font-mono text-[11px] text-ink">
                  <p className="text-sm tabular-nums">{fmt(Number(payload[0].value))}</p>
                  <p className="text-muted uppercase">
                    {label} · {String(payload[0].payload.date)}
                  </p>
                </div>
              ) : null
            }
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="currentColor"
            strokeWidth={1.75}
            dot={data.length < 24 ? { r: 2.5, fill: "var(--surface)", stroke: "currentColor", strokeWidth: 1.5 } : false}
            activeDot={{ r: 5, fill: "var(--ink)", stroke: "var(--surface)", strokeWidth: 2 }}
            isAnimationActive={!reduced}
            animationDuration={400}
            animationEasing="ease-out"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
