import { Trash2, Check, ChevronLeft, ChevronRight, Download, Link2, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type DeadlineItem, type JobStatus, type PipelineCard } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, Modal, PageHeader, Segmented, useToast } from "../components/ui";
import { withViewTransition } from "../lib/motion";
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
  overdue?: boolean;
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

function EventChip({
  e,
  onEdit,
  large,
  onDragStart,
}: {
  e: CalEvent;
  onEdit: (d: DeadlineItem) => void;
  large?: boolean;
  onDragStart?: (id: string) => void;
}) {
  const tone =
    e.kind === "follow_up"
      ? "border-dashed border-ink-2 text-ink-2"
      : e.done
        ? "border-line text-muted line-through"
        : e.overdue
          ? "border-alert bg-alert-soft text-alert"
          : e.urgent
            ? "border-ink bg-ink text-on-ink"
            : "border-ink text-ink";
  const body = (
    <>
      <span className={large ? "block font-medium" : "block truncate"}>{e.title}</span>
      {large && e.detail && <span className="mt-0.5 block font-mono text-[10px] uppercase opacity-75">{e.detail}</span>}
    </>
  );
  const base = cx("block w-full border px-1.5 py-1 text-left text-[11.5px] leading-tight transition-colors", tone);
  // A stable view-transition name lets a moved event glide to its new day.
  const vt = e.deadline ? { viewTransitionName: `ev-${e.deadline.id}` } : undefined;
  if (e.deadline) {
    const d = e.deadline;
    return (
      <button
        type="button"
        title={`${e.title}: click to edit, or drag to another day`}
        onClick={() => onEdit(d)}
        draggable={!e.done}
        onDragStart={(ev) => {
          ev.dataTransfer.setData("text/plain", d.id);
          ev.dataTransfer.effectAllowed = "move";
          onDragStart?.(d.id);
        }}
        className={cx(base, "cursor-grab hover:outline-1 hover:outline-ink active:cursor-grabbing")}
        style={vt}
      >
        {body}
      </button>
    );
  }
  return (
    <a href="#/pipeline" title={e.title} className={base}>
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
  const [moved, setMoved] = useState<Record<string, string>>({}); // optimistic due dates while a move saves
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const [deadlines, pipeline, jobs] = data.data ?? [[], [], []];
  useEffect(() => setMoved({}), [deadlines]);
  const events = useMemo(() => {
    const out: CalEvent[] = (deadlines as DeadlineItem[]).map((d) => {
      const due = moved[d.id] ?? d.due;
      return {
        date: due,
        title: d.title,
        kind: "deadline",
        done: d.done,
        overdue: !d.done && due < today(),
        urgent: !d.done && d.days_left <= 3,
        deadline: d,
        detail: d.kind.replace("_", " ") + (d.human_only ? " · needs you" : ""),
      };
    });
    for (const p of pipeline as PipelineCard[])
      if (p.follow_up && p.stage !== "done")
        out.push({ date: p.follow_up, title: `Follow up: ${p.title}`, kind: "follow_up", detail: `pipeline · ${p.stage}` });
    return out;
  }, [deadlines, pipeline, moved]);

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
  const move = async (id: string, due: string) => {
    const d = (deadlines as DeadlineItem[]).find((x) => x.id === id);
    if (!d || (moved[id] ?? d.due) === due) return;
    withViewTransition(() => setMoved((m) => ({ ...m, [id]: due })));
    const ok = await run(id, () => api.updateDeadline(id, { due }), `Moved to ${due}`);
    if (!ok) withViewTransition(() => setMoved((m) => Object.fromEntries(Object.entries(m).filter(([k]) => k !== id))));
  };
  const switchView = (v: "month" | "week") => {
    withViewTransition(() => setView(v));
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
    withViewTransition(
      () => (view === "month" ? setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + dir, 1)) : setWeekStart(addDays(weekStart, 7 * dir))),
      dir === 1 ? "next" : "prev",
    );
  const goToday = () =>
    withViewTransition(() => {
      setCursor(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
      setWeekStart(mondayOf(new Date()));
    });
  const heading =
    view === "month"
      ? cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
      : `${weekDays[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${weekDays[6].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

  return (
    <div>
      <PageHeader
        eyebrow={`${upcoming.length} open deadlines`}
        title="Calendar"
        subtitle="Deadlines and pipeline follow-ups. Click a deadline to edit it, or drag it to another day. calendar.ics in your workspace updates with every change."
        actions={
          <>
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(subscribe).then(() => toast("Subscribe link copied"))}>
              <Link2 /> Subscribe link
            </Button>
            <a href={api.calendarUrl} download="lighthouse.ics">
              <Button size="sm" tabIndex={-1}>
                <Download /> .ics
              </Button>
            </a>
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @5xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="card min-w-0 animate-rise">
          <div className="flex flex-wrap items-center gap-3 border-b border-frame px-5 py-4">
            <h2 className="display min-w-0 flex-1 text-4xl md:text-5xl" style={{ viewTransitionName: "cal-heading" }}>
              {heading}
            </h2>
            <div className="flex items-center gap-1">
              <Button size="sm" variant="ghost" className="px-2" aria-label={`Previous ${view}`} onClick={() => step(-1)}>
                <ChevronLeft />
              </Button>
              <Button size="sm" variant="ghost" onClick={goToday}>
                Today
              </Button>
              <Button size="sm" variant="ghost" className="px-2" aria-label={`Next ${view}`} onClick={() => step(1)}>
                <ChevronRight />
              </Button>
            </div>
            <Segmented label="Calendar view" size="sm" value={view} onChange={switchView} options={[{ value: "month", label: "Month" }, { value: "week", label: "Week" }]} />
          </div>
          <div className="overflow-x-auto">
            <div className="min-w-[640px]" style={{ viewTransitionName: "cal-grid" }}>
              <div className="grid grid-cols-7 border-b border-line">
                {(view === "month" ? WEEKDAYS : weekDays.map((d, i) => `${WEEKDAYS[i]} ${d.getDate()}`)).map((d) => (
                  <div key={d} className="eyebrow px-2.5 py-2">
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
                      onDragOver={(ev) => {
                        ev.preventDefault();
                        setDropTarget(key);
                      }}
                      onDragLeave={() => setDropTarget((t) => (t === key ? null : t))}
                      onDrop={(ev) => {
                        ev.preventDefault();
                        setDropTarget(null);
                        const id = ev.dataTransfer.getData("text/plain");
                        if (id) move(id, key);
                      }}
                      className={cx(
                        "border-r border-b border-line p-2 transition-colors duration-150 [&:nth-child(7n)]:border-r-0",
                        view === "month" ? "min-h-28" : "min-h-96",
                        dim && "bg-sunken/60 text-muted",
                        view === "week" && key === todayIso && "bg-sunken",
                        dropTarget === key && "bg-sunken outline-1 -outline-offset-1 outline-ink",
                      )}
                    >
                      {view === "month" && (
                        <div className={cx("num mb-1.5 flex size-6 items-center justify-center text-xs", key === todayIso ? "bg-ink text-on-ink" : dim ? "text-muted" : "text-ink-2")}>
                          {d.getDate()}
                        </div>
                      )}
                      <div className={cx("flex flex-col", view === "week" ? "gap-1.5" : "gap-1")}>
                        {dayEvents.map((e, i) => (
                          <EventChip key={e.deadline?.id ?? i} e={e} onEdit={setEditing} large={view === "week"} />
                        ))}
                        {view === "week" && !dayEvents.length && <span className="font-mono text-[11px] text-muted">—</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-8">
          <Card title="Add a deadline">
            <form
              className="grid gap-3 p-5"
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
              <div className="grid grid-cols-2 gap-3">
                <input type="date" required className="input" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} />
                <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {KINDS.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" disabled={busy === "add"}>
                <Plus /> Add deadline
              </Button>
            </form>
          </Card>

          <Card title="Upcoming">
            {upcoming.length ? (
              <ul>
                {upcoming.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 border-b border-line px-5 py-3 last:border-b-0">
                    <span className={cx("display w-14 shrink-0 text-2xl", d.days_left < 0 && "text-alert")}>
                      {d.days_left < 0 ? `-${-d.days_left}d` : `${d.days_left}d`}
                    </span>
                    <button className="min-w-0 flex-1 truncate text-left text-sm hover:underline" title={`${d.title}: edit`} onClick={() => setEditing(d)}>
                      {d.title}
                    </button>
                    <Button size="sm" variant="ghost" className="px-2" title="Mark done" aria-label={`Mark "${d.title}" done`} disabled={!!busy} onClick={() => run(d.id, () => api.updateDeadline(d.id, { done: true }), "Marked done")}>
                      <Check />
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing coming up.</Empty>
            )}
          </Card>

          <Card title="Recurring jobs">
            <ul>
              {(jobs as JobStatus[]).map((j) => (
                <li key={j.name} className="border-b border-line px-5 py-3 last:border-b-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-ink">{j.name}</span>
                    <Chip>{cronText(j.schedule)}</Chip>
                    <Button className="ml-auto" size="sm" variant="ghost" disabled={!!busy} onClick={() => run(`job-${j.name}`, () => api.runJob(j.name), `${j.name} ran`)}>
                      {busy === `job-${j.name}` ? "Running…" : "Run now"}
                    </Button>
                  </div>
                  <p className="mt-1 font-mono text-[10.5px] text-muted uppercase">
                    {j.next_run ? `next ${new Date(j.next_run).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "not scheduled"}
                    {j.last_run && ` · last ${new Date(j.last_run).toLocaleDateString()} ${j.ok ? "ok" : "failed"}`}
                    {j.error && <span className="text-alert"> · {j.error}</span>}
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
          onSave={async (changes) => {
            const id = editing.id;
            setEditing(null);
            if (changes.due && changes.due !== editing.due) withViewTransition(() => setMoved((m) => ({ ...m, [id]: changes.due! })));
            await run(id, () => api.updateDeadline(id, changes), "Deadline updated");
          }}
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
        <label className="flex items-center gap-2.5 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--ink)]" checked={f.human_only} onChange={(e) => setF({ ...f, human_only: e.target.checked })} />
          Needs me (shows in "This week" and gets a reminder)
        </label>
        <label className="flex items-center gap-2.5 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--ink)]" checked={f.done} onChange={(e) => setF({ ...f, done: e.target.checked })} />
          Done
        </label>
        <div className="mt-2 flex justify-between gap-2 border-t border-line pt-4">
          <Button type="button" variant="danger" disabled={busy} onClick={onDelete}>
            <Trash2 /> Delete
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
