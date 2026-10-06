import { useMemo, useState } from "react";
import { api, type DeadlineItem, type JobStatus, type PipelineCard } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, Modal, PageHeader, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

const KINDS = ["application", "submission", "filing", "follow_up", "personal", "other"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d: Date, n: number) => {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
};
const mondayOf = (d: Date) => addDays(new Date(d.getFullYear(), d.getMonth(), d.getDate()), -((d.getDay() + 6) % 7));

type CalEvent = {
  date: string;
  title: string;
  kind: "deadline" | "follow_up";
  done?: boolean;
  urgent?: boolean;
  deadline?: DeadlineItem;
  detail?: string;
};

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

function EventChip({ e, onEdit, large }: { e: CalEvent; onEdit: (d: DeadlineItem) => void; large?: boolean }) {
  const tone =
    e.kind === "follow_up"
      ? "bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200"
      : e.done
        ? "bg-zinc-100 text-zinc-400 line-through dark:bg-zinc-800"
        : e.urgent
          ? "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200"
          : "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200";
  const body = (
    <>
      <span className={large ? "block font-medium" : "truncate"}>{e.title}</span>
      {large && e.detail && <span className="block text-[11px] opacity-75">{e.detail}</span>}
    </>
  );
  if (e.deadline) {
    const d = e.deadline;
    return (
      <button type="button" title={`${e.title}: click to edit`} onClick={() => onEdit(d)} className={cx("w-full rounded px-1 py-0.5 text-left text-[11px] hover:ring-1 hover:ring-amber-500", !large && "truncate", tone)}>
        {body}
      </button>
    );
  }
  return (
    <a href="#/pipeline" title={e.title} className={cx("block rounded px-1 py-0.5 text-[11px]", !large && "truncate", tone)}>
      {body}
    </a>
  );
}

export default function Calendar() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => Promise.all([api.deadlines(), api.pipeline(), api.jobs()]), [version]);
  const [cursor, setCursor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [view, setView] = useState<"month" | "week">(() => {
    try {
      return localStorage.getItem("lh-cal-view") === "week" ? "week" : "month";
    } catch {
      return "month";
    }
  });
  const [form, setForm] = useState({ title: "", due: today(7), kind: "application" });
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<DeadlineItem | null>(null);

  const [deadlines, pipeline, jobs] = data.data ?? [[], [], []];
  const events = useMemo(() => {
    const out: CalEvent[] = (deadlines as DeadlineItem[]).map((d) => ({
      date: d.due,
      title: d.title,
      kind: "deadline",
      done: d.done,
      urgent: !d.done && d.days_left <= 3,
      deadline: d,
      detail: d.kind + (d.human_only ? " · needs you" : ""),
    }));
    for (const p of pipeline as PipelineCard[])
      if (p.follow_up && p.stage !== "done")
        out.push({ date: p.follow_up, title: `Follow up: ${p.title}`, kind: "follow_up", detail: `pipeline · ${p.stage}` });
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
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    } finally {
      setBusy(null);
    }
  };
  const switchView = (v: "month" | "week") => {
    setView(v);
    try {
      localStorage.setItem("lh-cal-view", v);
    } catch {
      /* storage unavailable */
    }
  };

  const todayIso = today();
  const subscribe = `webcal://${window.location.host}/calendar.ics`;
  const upcoming = (deadlines as DeadlineItem[]).filter((d) => !d.done && d.days_left >= -30);
  const monthStart = mondayOf(cursor);
  const monthDays = Array.from({ length: 42 }, (_, i) => addDays(monthStart, i));
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const step = (dir: 1 | -1) =>
    view === "month" ? setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + dir, 1)) : setWeekStart(addDays(weekStart, 7 * dir));
  const goToday = () => {
    setCursor(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
    setWeekStart(mondayOf(new Date()));
  };
  const heading =
    view === "month"
      ? cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
      : `${weekDays[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${weekDays[6].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Calendar"
        subtitle="Deadlines and pipeline follow-ups. Click a deadline to edit it. calendar.ics in your workspace updates with every change."
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
          <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
            <Button size="sm" variant="ghost" aria-label={`Previous ${view}`} onClick={() => step(-1)}>
              ‹
            </Button>
            <h2 className="min-w-40 text-center text-sm font-semibold">{heading}</h2>
            <Button size="sm" variant="ghost" aria-label={`Next ${view}`} onClick={() => step(1)}>
              ›
            </Button>
            <Button size="sm" variant="ghost" onClick={goToday}>
              Today
            </Button>
            <div className="ml-auto flex rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700" role="group" aria-label="Calendar view">
              {(["month", "week"] as const).map((v) => (
                <button
                  key={v}
                  aria-pressed={view === v}
                  onClick={() => switchView(v)}
                  className={cx("rounded px-2.5 py-0.5 text-xs font-medium capitalize", view === v ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-500")}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-7 border-b border-zinc-100 text-center text-[11px] font-medium text-zinc-500 dark:border-zinc-800">
            {(view === "month" ? WEEKDAYS : weekDays.map((d, i) => `${WEEKDAYS[i]} ${d.getDate()}`)).map((d) => (
              <div key={d} className="py-1.5">
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {(view === "month" ? monthDays : weekDays).map((d) => {
              const key = iso(d);
              const dim = view === "month" && d.getMonth() !== cursor.getMonth();
              const dayEvents = events.filter((e) => e.date === key);
              return (
                <div
                  key={key}
                  className={cx(
                    "border-r border-b border-zinc-100 p-1.5 text-xs dark:border-zinc-800 [&:nth-child(7n)]:border-r-0",
                    view === "month" ? "min-h-24" : "min-h-80",
                    dim && "bg-zinc-50/60 text-zinc-400 dark:bg-zinc-950/40",
                    view === "week" && key === todayIso && "bg-amber-50/40 dark:bg-amber-950/20",
                  )}
                >
                  {view === "month" && (
                    <div className={cx("mb-1 flex size-5 items-center justify-center rounded-full tabular-nums", key === todayIso && "bg-amber-500 font-semibold text-white")}>
                      {d.getDate()}
                    </div>
                  )}
                  <div className={cx("flex flex-col", view === "week" ? "gap-1" : "gap-0.5")}>
                    {dayEvents.map((e, i) => (
                      <EventChip key={i} e={e} onEdit={setEditing} large={view === "week"} />
                    ))}
                    {view === "week" && !dayEvents.length && <span className="text-[11px] text-zinc-300 dark:text-zinc-700">—</span>}
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
                run(
                  "add",
                  async () => {
                    await api.addDeadline(form);
                    setForm({ ...form, title: "" });
                  },
                  "Deadline added",
                );
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
                  <li key={d.id} className="flex items-center gap-1.5 px-3 py-2 text-sm">
                    <span className={cx("w-9 shrink-0 text-right text-xs font-semibold tabular-nums", d.days_left <= 3 ? "text-red-600" : d.days_left <= 14 ? "text-amber-600" : "text-zinc-500")}>
                      {d.days_left < 0 ? `${-d.days_left}d late` : `${d.days_left}d`}
                    </span>
                    <button className="min-w-0 flex-1 truncate text-left hover:underline" title={`${d.title}: edit`} onClick={() => setEditing(d)}>
                      {d.title}
                    </button>
                    <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run(d.id, () => api.updateDeadline(d.id, { done: true }), "Marked done")}>
                      Done
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

      {editing && (
        <EditDeadline
          d={editing}
          busy={busy === editing.id}
          onClose={() => setEditing(null)}
          onSave={async (changes) => (await run(editing.id, () => api.updateDeadline(editing.id, changes), "Deadline updated")) && setEditing(null)}
          onDelete={async () => (await run(editing.id, () => api.deleteDeadline(editing.id), "Deadline deleted")) && setEditing(null)}
        />
      )}
    </div>
  );
}

function EditDeadline({
  d,
  busy,
  onClose,
  onSave,
  onDelete,
}: {
  d: DeadlineItem;
  busy: boolean;
  onClose: () => void;
  onSave: (changes: Partial<DeadlineItem>) => void;
  onDelete: () => void;
}) {
  const [f, setF] = useState({ title: d.title, due: d.due, kind: d.kind, url: d.url ?? "", human_only: d.human_only, done: d.done });
  return (
    <Modal title="Edit deadline" onClose={onClose}>
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onSave({ ...f, url: f.url.trim() || null });
        }}
      >
        <label>
          <span className="label">Title</span>
          <input className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label>
            <span className="label">Due</span>
            <input type="date" required className="input" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} />
          </label>
          <label>
            <span className="label">Kind</span>
            <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              {KINDS.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          <span className="label">Link (optional)</span>
          <input className="input" type="url" placeholder="https://…" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.human_only} onChange={(e) => setF({ ...f, human_only: e.target.checked })} />
          Needs me (shows in "This week" and gets a reminder)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.done} onChange={(e) => setF({ ...f, done: e.target.checked })} />
          Done
        </label>
        <div className="flex justify-between gap-2">
          <Button type="button" variant="danger" disabled={busy} onClick={onDelete}>
            Delete
          </Button>
          <div className="flex gap-2">
            <Button type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={busy}>
              Save
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
