import { useMemo, useState } from "react";
import { api, type DeadlineItem, type JobStatus, type PipelineCard } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

const KINDS = ["application", "submission", "filing", "follow_up", "personal", "other"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

type CalEvent = { date: string; title: string; kind: "deadline" | "follow_up"; done?: boolean; urgent?: boolean };

function cronText(expr: string | null) {
  if (!expr) return "manual";
  const known: Record<string, string> = {
    "0 8 * * *": "daily 08:00",
    "0 7 * * *": "daily 07:00",
    "0 9 * * mon": "Mondays 09:00 (biweekly)",
    "0 17 * * fri": "Fridays 17:00",
  };
  return known[expr] ?? expr;
}

export default function Calendar() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => Promise.all([api.deadlines(), api.pipeline(), api.jobs()]), [version]);
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [form, setForm] = useState({ title: "", due: today(7), kind: "application" });
  const [busy, setBusy] = useState<string | null>(null);

  const [deadlines, pipeline, jobs] = data.data ?? [[], [], []];
  const events = useMemo(() => {
    const out: CalEvent[] = (deadlines as DeadlineItem[]).map((d) => ({
      date: d.due, title: d.title, kind: "deadline", done: d.done, urgent: !d.done && d.days_left <= 3,
    }));
    for (const p of pipeline as PipelineCard[])
      if (p.follow_up && p.stage !== "done") out.push({ date: p.follow_up, title: `Follow up: ${p.title}`, kind: "follow_up" });
    return out;
  }, [deadlines, pipeline]);

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;

  const run = async (key: string, fn: () => Promise<unknown>, msg: string) => {
    setBusy(key);
    try {
      await fn();
      toast(msg);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  // Month grid starting on Monday.
  const first = new Date(cursor);
  const start = new Date(first);
  start.setDate(1 - ((first.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
  const todayIso = today();
  const subscribe = `webcal://${window.location.host}/calendar.ics`;
  const upcoming = (deadlines as DeadlineItem[]).filter((d) => !d.done && d.days_left >= -30);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Calendar"
        subtitle="Deadlines and pipeline follow-ups. calendar.ics in your workspace updates with every change."
        actions={
          <>
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(subscribe).then(() => toast("Subscribe link copied"))}>
              Copy subscribe link
            </Button>
            <a href={api.calendarUrl} download="lighthouse.ics">
              <Button size="sm">Download .ics</Button>
            </a>
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <div className="flex items-center gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
            <Button size="sm" variant="ghost" aria-label="Previous month" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>
              ‹
            </Button>
            <h2 className="w-40 text-center text-sm font-semibold">
              {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </h2>
            <Button size="sm" variant="ghost" aria-label="Next month" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>
              ›
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCursor(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>
              Today
            </Button>
          </div>
          <div className="grid grid-cols-7 border-b border-zinc-100 text-center text-[11px] font-medium text-zinc-500 dark:border-zinc-800">
            {WEEKDAYS.map((d) => (
              <div key={d} className="py-1.5">
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((d) => {
              const key = iso(d);
              const inMonth = d.getMonth() === cursor.getMonth();
              const dayEvents = events.filter((e) => e.date === key);
              return (
                <div
                  key={key}
                  className={cx(
                    "min-h-24 border-r border-b border-zinc-100 p-1.5 text-xs dark:border-zinc-800 [&:nth-child(7n)]:border-r-0",
                    !inMonth && "bg-zinc-50/60 text-zinc-400 dark:bg-zinc-950/40",
                  )}
                >
                  <div className={cx("mb-1 flex size-5 items-center justify-center rounded-full tabular-nums", key === todayIso && "bg-amber-500 font-semibold text-white")}>
                    {d.getDate()}
                  </div>
                  <div className="flex flex-col gap-0.5">
                    {dayEvents.map((e, i) => (
                      <span
                        key={i}
                        title={e.title}
                        className={cx(
                          "truncate rounded px-1 py-0.5 text-[11px]",
                          e.kind === "follow_up"
                            ? "bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200"
                            : e.done
                              ? "bg-zinc-100 text-zinc-400 line-through dark:bg-zinc-800"
                              : e.urgent
                                ? "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200"
                                : "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
                        )}
                      >
                        {e.title}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="Add a deadline">
            <form
              className="grid gap-2 p-3"
              onSubmit={(e) => {
                e.preventDefault();
                run("add", async () => {
                  await api.addDeadline(form);
                  setForm({ ...form, title: "" });
                }, "Deadline added");
              }}
            >
              <input className="input" required placeholder="e.g. IEEE Senior Member application" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <div className="grid grid-cols-2 gap-2">
                <input type="date" required className="input" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} />
                <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {KINDS.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" size="sm" disabled={busy === "add"}>
                Add
              </Button>
            </form>
          </Card>

          <Card title="Upcoming">
            {upcoming.length ? (
              <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {upcoming.map((d) => (
                  <li key={d.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                    <span className={cx("w-9 shrink-0 text-right text-xs font-semibold tabular-nums", d.days_left < 0 ? "text-red-600" : d.days_left <= 3 ? "text-red-600" : d.days_left <= 14 ? "text-amber-600" : "text-zinc-500")}>
                      {d.days_left < 0 ? `${-d.days_left}d late` : `${d.days_left}d`}
                    </span>
                    <span className="min-w-0 flex-1 truncate" title={d.title}>
                      {d.title}
                    </span>
                    <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run(d.id, () => api.updateDeadline(d.id, { done: true }), "Marked done")}>
                      Done
                    </Button>
                    <Button size="sm" variant="danger" disabled={!!busy} aria-label={`Delete ${d.title}`} onClick={() => run(d.id, () => api.deleteDeadline(d.id), "Deleted")}>
                      ✕
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing coming up.</Empty>
            )}
          </Card>

          <Card title="Recurring jobs">
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {(jobs as JobStatus[]).map((j) => (
                <li key={j.name} className="px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs">{j.name}</span>
                    <Chip>{cronText(j.schedule)}</Chip>
                    <Button className="ml-auto" size="sm" variant="ghost" disabled={!!busy} onClick={() => run(`job-${j.name}`, () => api.runJob(j.name), `${j.name} ran`)}>
                      {busy === `job-${j.name}` ? "Running…" : "Run now"}
                    </Button>
                  </div>
                  <p className="mt-0.5 text-[11px] text-zinc-500">
                    {j.next_run ? `next ${new Date(j.next_run).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "not scheduled"}
                    {j.last_run && ` · last ${new Date(j.last_run).toLocaleDateString()} ${j.ok ? "✓" : "✗"}`}
                    {j.error && <span className="text-red-600"> · {j.error}</span>}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
