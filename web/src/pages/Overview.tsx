import type { Overview } from "../api";
import Sparkline from "../components/Sparkline";
import { Card, cx, Delta, Empty, ErrorBox, fmt, Loading, STATUS_STYLE } from "../components/ui";

const metricLabel: Record<string, string> = {
  stars: "stars",
  forks: "forks",
  downloads: "downloads / 30d",
  downloads_all_time: "downloads",
  likes: "likes",
  views: "views / day",
};

export default function OverviewPage({ data, error, retry }: { data: Overview | null; error: Error | null; retry: () => void }) {
  if (error && !data) return <ErrorBox error={error} retry={retry} />;
  if (!data) return <Loading />;
  const board = data.scoreboard;
  const remaining = Math.max(0, board.threshold - board.banked);
  const target = data.person.filing_target?.target_date;
  const daysToFiling = target ? Math.ceil((new Date(target).getTime() - Date.now()) / 86_400_000) : null;
  const slots = Math.max(board.target, board.banked + board.building);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      {/* progress */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{board.profile_name}</h1>
            <span className={cx("text-xs font-medium", remaining ? "text-amber-700 dark:text-amber-400" : "text-emerald-700 dark:text-emerald-400")}>
              {remaining ? `${remaining} more ${remaining > 1 ? "criteria" : "criterion"} to reach the threshold` : "Threshold met — keep building toward the target"}
            </span>
          </div>
          <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
            <a href="#/evidence" className="hover:text-amber-600">
              {board.banked}
            </a>
            <span className="text-zinc-400"> banked</span>
            <span className="mx-2 text-zinc-300 dark:text-zinc-600">/</span>
            {board.threshold}
            <span className="text-zinc-400"> needed</span>
            <span className="ml-3 text-base font-normal text-zinc-500">
              target {board.target} · {board.building} building
            </span>
          </p>
          <div className="mt-3 flex gap-1" aria-label={`${board.banked} of ${board.target} target criteria banked`}>
            {Array.from({ length: slots }, (_, i) => (
              <div
                key={i}
                className={cx(
                  "h-2 flex-1 rounded-full",
                  i < board.banked ? "bg-emerald-500" : i < board.banked + board.building ? "bg-amber-400/70" : "bg-zinc-200 dark:bg-zinc-800",
                  i === board.threshold - 1 && "ring-2 ring-zinc-900/70 ring-offset-1 dark:ring-white/60 dark:ring-offset-zinc-900",
                )}
                title={i === board.threshold - 1 ? "threshold" : undefined}
              />
            ))}
          </div>
        </Card>
        <div className="grid grid-cols-2 gap-4">
          <a href="#/inbox" className="card block p-4 hover:border-amber-400">
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Inbox</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{data.inbox_pending}</p>
            <p className="text-xs text-zinc-500">candidates to review</p>
          </a>
          <div className="card p-4">
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Filing target</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{daysToFiling !== null ? `${daysToFiling}d` : "—"}</p>
            <p className="text-xs text-zinc-500">{target ?? "set in data/person.json"}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* scoreboard */}
        <Card
          title="Criteria scoreboard"
          className="lg:col-span-2"
          actions={
            <a href="#/evidence" className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
              Evidence →
            </a>
          }
        >
          <ul className="grid divide-zinc-100 sm:grid-cols-2 dark:divide-zinc-800">
            {board.criteria.map((c) => (
              <li key={c.id} className="border-b border-zinc-100 last:border-b-0 sm:odd:border-r dark:border-zinc-800">
                <a href={`#/evidence?c=${c.id}`} className="flex items-start gap-2.5 px-4 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800/50" title={c.reason}>
                  <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", STATUS_STYLE[c.status].dot)} />
                  <span className="min-w-0 flex-1">
                    <span className={cx("block truncate text-sm", c.status === "dropped" && "text-zinc-400 line-through")}>{c.label}</span>
                    <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                      {STATUS_STYLE[c.status].label}
                      {c.status === "building" && c.needed_exhibits > 0 && ` · needs ${c.needed_exhibits} more`}
                      {c.matched_signals.length > 0 && ` · ${c.matched_signals.length} signal${c.matched_signals.length > 1 ? "s" : ""}`}
                    </span>
                  </span>
                  <span className="text-sm font-medium tabular-nums text-zinc-500" aria-label={`${c.exhibit_count} exhibits`}>
                    {c.exhibit_count}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="This week — only you can do these">
            {data.tasks.length ? (
              <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.tasks.slice(0, 5).map((t, i) => (
                  <li key={i} className="flex items-start gap-2 px-4 py-2 text-sm">
                    <span className="mt-0.5 text-zinc-400" aria-hidden>
                      ☐
                    </span>
                    <span className="min-w-0 flex-1">
                      {t.link ? (
                        <a href={t.link} className="link" target={t.link.startsWith("#") ? undefined : "_blank"} rel="noreferrer">
                          {t.title}
                        </a>
                      ) : (
                        t.title
                      )}
                    </span>
                    {t.due && <span className="shrink-0 text-xs text-zinc-500 tabular-nums">{t.due.slice(5)}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing needs you this week.</Empty>
            )}
          </Card>
          <Card title="Next deadlines">
            {data.deadlines.length ? (
              <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.deadlines.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <span
                      className={cx(
                        "w-10 shrink-0 text-right text-xs font-semibold tabular-nums",
                        d.days_left <= 7 ? "text-red-600 dark:text-red-400" : d.days_left <= 14 ? "text-amber-600" : "text-zinc-500",
                      )}
                    >
                      {d.days_left}d
                    </span>
                    <span className="min-w-0 flex-1 truncate">
                      {d.url ? (
                        <a href={d.url} className="link" target="_blank" rel="noreferrer">
                          {d.title}
                        </a>
                      ) : (
                        d.title
                      )}
                    </span>
                    <span className="text-xs text-zinc-500 tabular-nums">{d.due}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No upcoming deadlines in data/deadlines.json.</Empty>
            )}
          </Card>
        </div>
      </div>

      {/* sparklines */}
      <Card
        title="Metrics"
        actions={
          <a href="#/metrics" className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
            All metrics →
          </a>
        }
      >
        {data.sparklines.length ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-px bg-zinc-100 dark:bg-zinc-800">
            {data.sparklines.map((s) => (
              <a
                key={`${s.source}:${s.item}:${s.metric}`}
                href={`#/metrics?item=${encodeURIComponent(s.item)}`}
                className="bg-white px-4 py-2.5 hover:bg-zinc-50 dark:bg-zinc-900 dark:hover:bg-zinc-800/60"
              >
                <p className="truncate text-xs text-zinc-500 dark:text-zinc-400" title={s.item}>
                  {s.item.replace(/^datasets\//, "")}
                </p>
                <p className="mt-0.5 flex items-baseline gap-1.5">
                  <span className="text-lg font-semibold tabular-nums">{fmt(s.value)}</span>
                  <span className="text-xs text-zinc-500">{metricLabel[s.metric] ?? s.metric}</span>
                </p>
                <Sparkline points={s.points} />
                <p className="text-[11px] text-zinc-500">
                  <Delta value={s.delta} /> since {s.previous_date?.slice(5) ?? "—"}
                </p>
              </a>
            ))}
          </div>
        ) : (
          <Empty>
            No metrics yet — <a href="#/sources" className="link">add a source</a>, then take a snapshot.
          </Empty>
        )}
      </Card>
    </div>
  );
}
