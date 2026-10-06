import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Series } from "../api";
import { useRefresh } from "../App";
import { Button, Card, cx, Delta, Empty, ErrorBox, fmt, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const ORDER = ["stars", "forks", "watchers", "contributors", "releases", "downloads", "downloads_all_time", "likes", "upvotes", "views", "views_unique", "clones", "clones_unique", "open_issues"];

export default function Metrics({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const metrics = useLoad(() => api.metrics(), [version]);
  const [source, setSource] = useState<string>("all");
  const [busy, setBusy] = useState(false);

  const items = useMemo(() => {
    const map = new Map<string, Series[]>();
    for (const s of metrics.data?.series ?? []) {
      if (source !== "all" && s.source !== source) continue;
      const key = `${s.source}|${s.item}`;
      map.set(key, [...(map.get(key) ?? []), s]);
    }
    for (const list of map.values()) list.sort((a, b) => idx(a.metric) - idx(b.metric));
    return [...map.entries()];
  }, [metrics.data, source]);

  useEffect(() => {
    if (focus && metrics.data) document.getElementById(`item-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus, metrics.data]);

  const snapshot = async () => {
    setBusy(true);
    try {
      const { reports } = await api.snapshot();
      const rows = reports.reduce((n, r) => n + r.metrics_written, 0);
      const errors = reports.flatMap((r) => r.errors);
      toast(errors.length ? `Snapshot: ${rows} rows, ${errors.length} error(s): ${errors[0]}` : `Snapshot: ${rows} new or changed rows`, errors.length ? "error" : "ok");
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (metrics.error) return <ErrorBox error={metrics.error} retry={metrics.reload} />;
  if (!metrics.data) return <Loading />;
  const sources = [...new Set(metrics.data.series.map((s) => s.source))];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Metrics"
        subtitle="Dated snapshots from data/metrics.csv. Deltas compare the last two snapshots."
        actions={
          <>
            <select className="input w-auto" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Filter by source">
              <option value="all">All sources</option>
              {sources.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <a href={api.exportUrl} download>
              <Button>Export CSV</Button>
            </a>
            <Button variant="primary" disabled={busy} onClick={snapshot}>
              {busy ? "Snapshotting…" : "Snapshot now"}
            </Button>
          </>
        }
      />
      {items.length === 0 ? (
        <Card>
          <Empty>
            No metrics yet. <a href="#/sources" className="link">Add a source</a>, then press Snapshot now.
          </Empty>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map(([key, series]) => (
            <ItemCard key={key} series={series} highlighted={series[0].item === focus} />
          ))}
        </div>
      )}
    </div>
  );
}

const idx = (m: string) => {
  const i = ORDER.indexOf(m);
  return i === -1 ? ORDER.length : i;
};

function ItemCard({ series, highlighted }: { series: Series[]; highlighted: boolean }) {
  const [active, setActive] = useState(series[0].metric);
  const current = series.find((s) => s.metric === active) ?? series[0];
  const { source, item, url } = series[0];
  return (
    <section id={`item-${item}`} className={cx("card scroll-mt-4", highlighted && "ring-2 ring-amber-400")}>
      <header className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
        <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{source}</span>
        <h2 className="text-sm font-semibold">
          {url ? (
            <a href={url} target="_blank" rel="noreferrer" className="link">
              {item}
            </a>
          ) : (
            item
          )}
        </h2>
      </header>
      <div className="grid gap-0 md:grid-cols-[220px_1fr]">
        <ul className="flex gap-1 overflow-x-auto border-b border-zinc-100 p-2 md:flex-col md:border-r md:border-b-0 dark:border-zinc-800" role="tablist">
          {series.map((s) => (
            <li key={s.metric}>
              <button
                role="tab"
                aria-selected={s.metric === active}
                onClick={() => setActive(s.metric)}
                className={cx(
                  "flex w-full items-baseline justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-sm whitespace-nowrap",
                  s.metric === active ? "bg-zinc-100 dark:bg-zinc-800" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50",
                )}
              >
                <span className="text-zinc-600 dark:text-zinc-300">{s.metric.replace(/_/g, " ")}</span>
                <span className="flex items-baseline gap-1.5">
                  <span className="font-semibold tabular-nums">{fmt(s.value)}</span>
                  <span className="text-[11px]">
                    <Delta value={s.delta} />
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="h-56 p-3 text-zinc-500">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={current.points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} minTickGap={24} />
              <YAxis tickFormatter={(v: number) => compact(v)} tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} width={44} domain={["auto", "auto"]} />
              <Tooltip
                formatter={(v) => [fmt(Number(v)), current.metric.replace(/_/g, " ")]}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid rgb(228 228 231)" }}
              />
              <Line type="monotone" dataKey="value" stroke="#f59e0b" strokeWidth={2} dot={current.points.length < 20 ? { r: 2.5 } : false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

function compact(v: number) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(v);
}
