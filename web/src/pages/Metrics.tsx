import { useEffect, useMemo, useState } from "react";
import { api, type Series } from "../api";
import { useRefresh } from "../App";
import { Camera, Download } from "lucide-react";
import TrendChart, { inRange, RangePicker, type Range } from "../components/TrendChart";
import { Button, Card, Chip, cx, Delta, Empty, ErrorBox, Loading, PageHeader, plural, useToast } from "../components/ui";
import { CountUp } from "../lib/motion";
import { useLoad } from "../hooks";

const ORDER = ["stars", "forks", "watchers", "contributors", "releases", "downloads", "downloads_all_time", "likes", "upvotes", "views", "views_unique", "clones", "clones_unique", "open_issues"];

export default function Metrics({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const metrics = useLoad(() => api.metrics(), [version]);
  const [source, setSource] = useState<string>("all");
  const [busy, setBusy] = useState(false);
  const [range, setRange] = useState<Range>("all");

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
      toast(errors.length ? `Snapshot: ${plural(rows, "row")}, ${plural(errors.length, "error")}: ${errors[0]}` : `Snapshot: ${plural(rows, "new or changed row")}`, errors.length ? "error" : "ok");
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
    <div>
      <PageHeader
        eyebrow={`${plural(items.length, "item")} · ${metrics.data.series.length} series`}
        title="Metrics"
        subtitle="Dated snapshots from data/metrics.csv. Deltas compare the last two snapshots."
        actions={
          <>
            <RangePicker value={range} onChange={setRange} />
            <select className="input h-8 w-auto py-0 font-mono text-[11px]" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Filter by source">
              <option value="all">All sources</option>
              {sources.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <a href={api.exportUrl} download>
              <Button size="sm" tabIndex={-1}>
                <Download /> CSV
              </Button>
            </a>
            <Button size="sm" variant="primary" disabled={busy} onClick={snapshot}>
              <Camera /> {busy ? "Snapshotting…" : "Snapshot now"}
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
        <div className="flex flex-col gap-8">
          {items.map(([key, series]) => (
            <ItemCard key={key} series={series} highlighted={series[0].item === focus} range={range} />
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

function ItemCard({ series, highlighted, range }: { series: Series[]; highlighted: boolean; range: Range }) {
  const [active, setActive] = useState(series[0].metric);
  const current = series.find((s) => s.metric === active) ?? series[0];
  const { source, item, url } = series[0];
  const points = inRange(current.points, range);
  return (
    <section id={`item-${item}`} className={cx("card animate-rise scroll-mt-6", highlighted && "outline-2 outline-offset-2 outline-ink")}>
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-4">
        <Chip>{source}</Chip>
        <h2 className="min-w-0 truncate text-lg font-medium">
          {url ? (
            <a href={url} target="_blank" rel="noreferrer" className="link">
              {item}
            </a>
          ) : (
            item
          )}
        </h2>
      </header>
      <div className="grid @3xl:grid-cols-[260px_minmax(0,1fr)]">
        <ul className="flex overflow-x-auto border-b border-line @3xl:max-h-[400px] @3xl:flex-col @3xl:overflow-x-hidden @3xl:overflow-y-auto @3xl:border-r @3xl:border-b-0" role="tablist">
          {series.map((s) => (
            <li key={s.metric} className="shrink-0 border-r border-line @3xl:border-r-0 @3xl:border-b">
              <button
                role="tab"
                aria-selected={s.metric === active}
                onClick={() => setActive(s.metric)}
                className={cx(
                  "flex w-full flex-col gap-1 px-5 py-3.5 text-left whitespace-nowrap transition-colors duration-150",
                  s.metric === active ? "bg-ink text-on-ink" : "hover:bg-sunken",
                )}
              >
                <span className={cx("eyebrow", s.metric === active && "text-on-ink/70")}>{s.metric.replace(/_/g, " ")}</span>
                <span className="flex items-baseline gap-2">
                  <span className="display text-3xl">
                    <CountUp value={s.value} />
                  </span>
                  <span className="text-[11px]">
                    <Delta value={s.delta} />
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="min-w-0 p-5">
          <TrendChart points={points} label={current.metric.replace(/_/g, " ")} height={360} />
        </div>
      </div>
    </section>
  );
}
