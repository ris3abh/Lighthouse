import { ArrowRight, ArrowUp } from "lucide-react";
import { useRef } from "react";
import type { Overview } from "../api";
import Briefing from "../components/Briefing";
import Sparkline from "../components/Sparkline";
import { Card, CriterionName, cx, Delta, Empty, ErrorBox, Loading, plural, StatusBadge, StatusMark } from "../components/ui";
import { CountUp, useInView } from "../lib/motion";

const metricLabel: Record<string, string> = {
  stars: "stars",
  forks: "forks",
  downloads: "downloads / 30d",
  downloads_all_time: "downloads",
  likes: "likes",
  views: "views / day",
  citations: "citations",
  h_index: "h-index",
};

/** One segment per criterion slot; each fills to its level (banked full, building half) when it comes into view. */
function ScoreBar({ banked, building, slots, threshold, target }: { banked: number; building: number; slots: number; threshold: number; target: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useInView(ref);
  return (
    <div ref={ref} className="relative mt-8 flex gap-1.5" role="img" aria-label={`${banked} of ${target} target criteria banked, ${building} building`}>
      {Array.from({ length: slots }, (_, i) => {
        const fill = i < banked ? 100 : i < banked + building ? 50 : 0;
        const tone = i < banked ? "bg-banked" : "bg-building";
        return (
          <div key={i} className="relative flex-1">
            <div className="h-3 border border-ink">
              <div
                className={cx("h-full transition-[width] duration-[400ms] ease-out", tone)}
                style={{ width: seen ? `${fill}%` : 0, transitionDelay: `${i * 60}ms` }}
              />
            </div>
            {i === threshold - 1 && (
              <span className="absolute top-5 right-0 inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] text-ink uppercase">
                <ArrowUp className="size-3" aria-hidden /> threshold
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function More({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} className="inline-flex items-center gap-1 font-mono text-[11px] tracking-[0.1em] text-ink-2 uppercase hover:text-ink">
      {children}
      <ArrowRight className="size-3.5" aria-hidden />
    </a>
  );
}

export default function OverviewPage({ data, error, retry }: { data: Overview | null; error: Error | null; retry: () => void }) {
  if (error && !data) return <ErrorBox error={error} retry={retry} />;
  if (!data) return <Loading />;
  const board = data.scoreboard;
  const remaining = Math.max(0, board.threshold - board.banked);
  const target = data.person.filing_target?.target_date;
  const daysToFiling = target ? Math.ceil((new Date(target).getTime() - Date.now()) / 86_400_000) : null;
  const slots = Math.max(board.target, board.banked + board.building);

  return (
    <div className="flex flex-col gap-8">
      {/* hero: where the case stands */}
      <section className="card grid animate-rise grid-cols-2 @2xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] @5xl:grid-cols-[2fr_1fr_1fr]">
        <div className="col-span-2 border-b border-line p-5 md:p-8 @2xl:col-span-1 @2xl:row-span-2 @2xl:border-r @2xl:border-b-0 @5xl:row-span-1">
          <p className="eyebrow">{board.profile_name}</p>
          <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-2">
            <a href="#/evidence" className="display text-[88px] leading-[0.8] hover:text-ink-2 md:text-[132px]" aria-label={`${board.banked} banked of ${board.threshold} needed`}>
              <CountUp value={board.banked} />
              <span className="text-muted">/{board.threshold}</span>
            </a>
            <div className="pb-2 font-mono text-xs leading-relaxed text-ink-2">
              <p>CRITERIA BANKED / NEEDED</p>
              <p>
                TARGET {board.target} · {board.building} BUILDING
              </p>
            </div>
          </div>
          <ScoreBar banked={board.banked} building={board.building} slots={slots} threshold={board.threshold} target={board.target} />
          <p className="mt-10 text-[15px] text-ink-2">
            {remaining
              ? `${plural(remaining, "more criterion", "more criteria")} to reach the threshold.`
              : "Threshold met. Keep building toward the target."}
          </p>
        </div>
        <a
          href="#/inbox"
          className="group flex flex-col justify-between gap-3 border-r border-line p-4 hover:bg-sunken md:p-6 @2xl:border-r-0 @2xl:border-b @5xl:border-r @5xl:border-b-0 @5xl:p-8"
        >
          <p className="eyebrow">Inbox</p>
          <p className={cx("display text-5xl @2xl:text-7xl @5xl:my-6 @5xl:text-8xl", daysToFiling !== null && daysToFiling < 0 && "text-alert")}>
            <CountUp value={data.inbox_pending} />
          </p>
          <p className="flex items-center justify-between font-mono text-[11px] text-ink-2 uppercase">
            {data.inbox_pending === 1 ? "candidate" : "candidates"} to review
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
          </p>
        </a>
        <div className="flex flex-col justify-between gap-3 p-4 md:p-6 @5xl:p-8">
          <p className="eyebrow">Filing target</p>
          <p className="display text-5xl @2xl:text-7xl @5xl:my-6 @5xl:text-8xl">
            {daysToFiling !== null ? <CountUp value={daysToFiling} /> : "—"}
            {daysToFiling !== null && <span className="text-muted">d</span>}
          </p>
          <p className="font-mono text-[11px] text-ink-2 uppercase">{target ?? "Not set yet"}</p>
        </div>
      </section>

      <Briefing tasks={data.tasks} />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @2xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card title="Criteria scoreboard" className="@container" actions={<More href="#/evidence">Evidence</More>}>
          <ul className="grid @xl:grid-cols-2">
            {board.criteria.map((c) => (
              <li key={c.id} className="border-b border-line @xl:odd:border-r">
                <a href={`#/evidence?c=${c.id}`} className="flex h-full items-start gap-4 px-5 py-4 transition-colors hover:bg-sunken" title={c.reason}>
                  <StatusMark status={c.status} className="mt-1.5" />
                  <span className="min-w-0 flex-1">
                    <CriterionName c={c} className={cx("block text-lg leading-snug font-medium", c.status === "dropped" && "text-muted line-through")} />
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-ink-2">
                      <StatusBadge status={c.status} />
                      {c.status === "building" && c.needed_exhibits > 0 && <span className="uppercase">· needs {plural(c.needed_exhibits, "more exhibit")}</span>}
                      {c.in_progress_count > 0 && <span className="uppercase">· {c.in_progress_count} in progress</span>}
                      {c.matched_signals.length > 0 && <span className="uppercase">· {plural(c.matched_signals.length, "signal")}</span>}
                    </span>
                  </span>
                  <span className="display text-4xl text-ink-2" aria-label={`${c.exhibit_count} exhibits`}>
                    {c.exhibit_count}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </Card>

        <div className="flex flex-col gap-8">
          <Card title="Next deadlines" actions={<More href="#/calendar">Calendar</More>}>
            {data.deadlines.length ? (
              <ul>
                {data.deadlines.map((d) => (
                  <li key={d.id} className="flex items-baseline gap-4 border-b border-line px-5 py-3.5 last:border-b-0">
                    <span className={cx("display w-12 shrink-0 text-3xl", d.days_left < 0 && "text-alert")}>
                      {d.days_left < 0 ? `${-d.days_left}d` : `${d.days_left}d`}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px]">
                        {d.url ? (
                          <a href={d.url} className="link" target="_blank" rel="noreferrer">
                            {d.title}
                          </a>
                        ) : (
                          d.title
                        )}
                      </span>
                      <span className={cx("num text-[11px]", d.days_left < 0 ? "text-alert" : "text-ink-2")}>
                        {d.days_left < 0 ? "OVERDUE · " : ""}
                        {d.due}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No upcoming deadlines.</Empty>
            )}
          </Card>
        </div>
      </div>

      <Card title="Metrics" actions={<More href="#/metrics">All metrics</More>}>
        {data.sparklines.length ? (
          <div className="grid grid-cols-1 gap-px bg-line @2xl:grid-cols-2 @5xl:grid-cols-3">
            {data.sparklines.map((s) => (
              <a
                key={`${s.source}:${s.item}:${s.metric}`}
                href={`#/metrics?item=${encodeURIComponent(s.item)}`}
                className="flex flex-col gap-3 bg-surface px-5 py-5 transition-colors hover:bg-sunken"
              >
                <p className="num truncate text-[11px] text-ink-2" title={s.item}>
                  {s.item.replace(/^datasets\//, "")}
                </p>
                <p className="flex items-baseline gap-2">
                  <span className="display text-5xl">
                    <CountUp value={s.value} />
                  </span>
                  <span className="font-mono text-[11px] text-muted uppercase">{metricLabel[s.metric] ?? s.metric}</span>
                </p>
                <Sparkline points={s.points} className="h-12 w-full" />
                <p className="flex items-center gap-2 font-mono text-[11px] text-muted">
                  <Delta value={s.delta} /> SINCE {s.previous_date?.slice(5) ?? "—"}
                </p>
              </a>
            ))}
          </div>
        ) : (
          <Empty>
            No metrics yet. <a href="#/sources" className="link">Add a source</a>, then take a snapshot.
          </Empty>
        )}
      </Card>
    </div>
  );
}
