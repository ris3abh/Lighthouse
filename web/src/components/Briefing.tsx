import { useEffect, useState } from "react";
import { Square } from "lucide-react";
import { api, type Task } from "../api";
import { useRefresh } from "../App";
import { useLoad, useOnce } from "../hooks";
import RuleCheckView from "./RuleCheck";
import { Button, Card, Chip, cx, useToast } from "./ui";

/** The agent-written "what changed / 3 things to do this week", refreshed by the daily mission. */
export default function Briefing({ tasks = [] }: { tasks?: Task[] }) {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const once = useOnce(); // a briefing is a model run: once per click (B3)
  const brief = useLoad(() => api.briefing(), [version]);
  const [busy, setBusy] = useState<string | null>(null);
  const b = brief.data;
  const refreshing = b?.refreshing ?? null;

  // While the daily mission is writing a new briefing, poll until it lands.
  useEffect(() => {
    if (!refreshing) return;
    const t = window.setInterval(() => brief.reload(), 3000);
    return () => window.clearInterval(t);
  }, [refreshing]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () =>
    once.run("briefing", async () => {
      try {
        await api.runMission("what_changed");
        toast("Refreshing the briefing…");
        brief.reload();
      } catch (e) {
        toast((e as Error).message, "error");
      }
    });

  const decide = async (id: string, approve: boolean) => {
    setBusy(id);
    try {
      if (approve) await api.accept(id, {});
      else await api.reject(id);
      toast(approve ? "Approved" : "Dismissed");
      bump();
    } catch (e) {
      toast(`${(e as Error).message}. Open it in the Inbox to edit first.`, "error");
    } finally {
      setBusy(null);
    }
  };

  const actions = (
    <span className="flex items-center gap-2">
      {b?.generated_at && (
        <a href={`#/agent?run=${b.run_id}`} className="font-mono text-[11px] text-muted uppercase hover:text-ink">
          {new Date(b.generated_at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" })}
        </a>
      )}
      <Button size="sm" variant="ghost" disabled={!!refreshing || once.busy("briefing")} onClick={refresh}>
        {refreshing ? "Refreshing…" : "Refresh"}
      </Button>
    </span>
  );

  if (!b) return null;
  const mine = <MyTasks tasks={tasks} />;
  if (!b.generated_at)
    return (
      <Card title="This week" panel="briefing inbox deadlines pipeline" actions={actions} className="@container">
        <div className="grid gap-px bg-line @2xl:grid-cols-2">
          <p className="bg-surface p-6 text-[15px] leading-relaxed text-ink-2">
            No briefing yet. Press Refresh for one now, or turn on the daily what-changed mission in{" "}
            <a className="link" href="#/settings">
              Settings
            </a>{" "}
            to get one every morning.
          </p>
          {mine}
        </div>
      </Card>
    );

  return (
    <Card title="This week" panel="briefing inbox deadlines pipeline" actions={actions} className="@container">
      <div className="grid gap-px bg-line @2xl:grid-cols-2 @5xl:grid-cols-3">
        <div className="bg-surface p-6">
          <h3 className="eyebrow mb-4">
            What changed{b.since ? ` since ${new Date(b.since + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}` : ""}
          </h3>
          {b.changed.length ? (
            <ul className="space-y-3 text-[15px] leading-snug">
              {b.changed.map((c, i) => (
                <li key={i} className="flex gap-3">
                  <span className="mt-2 size-1.5 shrink-0 bg-ink" aria-hidden />
                  {c}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[15px] text-ink-2">Nothing worth noting.</p>
          )}
        </div>
        <div className="bg-surface p-6">
          <h3 className="eyebrow mb-4">Three things to do</h3>
          <ol className="space-y-5">
            {b.todos.map((t, i) => {
              const c = t.candidate;
              const open = c && c.status === "pending";
              return (
                <li key={i} className={cx("flex gap-4 text-[15px]", c && !open && "opacity-50")}>
                  <span className="display w-6 shrink-0 text-4xl leading-none">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium leading-snug">
                      {t.link && !c ? (
                        <a className="link" href={t.link} {...(t.link.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
                          {t.title}
                        </a>
                      ) : (
                        t.title
                      )}
                    </p>
                    {t.why && <p className="mt-1 text-sm text-ink-2">{t.why}</p>}
                    {c && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Chip>{c.kind}</Chip>
                        {c.source_tier === "self_reported" && <Chip tone="outline">self-reported</Chip>}
                        {open ? (
                          <>
                            <Button size="sm" variant="primary" disabled={busy === c.id} onClick={() => decide(c.id, true)}>
                              Approve
                            </Button>
                            <Button size="sm" disabled={busy === c.id} onClick={() => decide(c.id, false)}>
                              Dismiss
                            </Button>
                            <a className="link font-mono text-[11px] text-ink-2 uppercase" href="#/inbox">
                              review in Inbox
                            </a>
                          </>
                        ) : (
                          <span className="text-[11px] text-muted">{c.status === "rejected" ? "dismissed" : c.status}</span>
                        )}
                      </div>
                    )}
                    {t.candidate_id && !c && <p className="text-[11px] text-muted">done</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
        {mine}
      </div>
      {b.rule_check && b.rule_check.claims.length > 0 && (
        <div className="border-t border-line px-6 py-4">
          <RuleCheckView
            check={b.rule_check}
            compact
            onRecheck={() =>
              api
                .recheckBriefing()
                .then(() => brief.reload())
                .catch((e: Error) => toast(e.message, "error"))
            }
          />
        </div>
      )}
      <p className="border-t border-line px-6 py-3 font-mono text-[10.5px] text-muted uppercase">
        Written by the agent from your workspace. Opinions, not legal advice.
      </p>
    </Card>
  );
}

/** Things only the person can do (sign, send, submit): from the workspace, not the agent. Self-reported to-dos
 * (from onboarding) carry their criterion and can be ticked off; ticking one never banks anything. */
function MyTasks({ tasks }: { tasks: Task[] }) {
  const toast = useToast();
  const { bump } = useRefresh();
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [all, setAll] = useState(false);
  const open = tasks.filter((t) => !t.id || !closed.has(t.id));
  const shown = all ? open : open.slice(0, 6);
  const tick = async (t: Task) => {
    if (!t.id) return;
    setClosed((s) => new Set(s).add(t.id!));
    try {
      await api.updateTodo(t.id, "done");
      toast("Ticked off. Upload the proof to the Inbox when you have it; that's what counts.");
      bump();
    } catch (e) {
      setClosed((s) => {
        const n = new Set(s);
        n.delete(t.id!);
        return n;
      });
      toast((e as Error).message, "error");
    }
  };
  return (
    <div className="bg-surface p-6">
      <h3 className="eyebrow mb-4">Only you can do these</h3>
      {shown.length ? (
        <ul className="space-y-3">
          {shown.map((t, i) => (
            <li key={t.id ?? i} className="flex animate-rise items-start gap-3 text-[15px] leading-snug">
              {t.id ? (
                <button type="button" onClick={() => tick(t)} className="mt-1 shrink-0 text-ink-2 hover:text-ink" aria-label={`Mark done: ${t.title}`}>
                  <Square className="size-3.5" strokeWidth={1.5} aria-hidden />
                </button>
              ) : (
                <Square className="mt-1 size-3.5 shrink-0 text-ink-2" strokeWidth={1.5} aria-hidden />
              )}
              <span className="min-w-0 flex-1">
                {t.link ? (
                  <a href={t.link} className="link" target={t.link.startsWith("#") ? undefined : "_blank"} rel="noreferrer">
                    {t.title}
                  </a>
                ) : (
                  t.title
                )}
                {t.self_reported && (
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    {t.criterion_label && <Chip tone="outline">{t.criterion_label}</Chip>}
                    <span className="font-mono text-[10px] tracking-[0.06em] text-muted uppercase">You told me · not evidence yet</span>
                  </span>
                )}
              </span>
              {t.due && <span className="num shrink-0 text-xs text-ink-2">{t.due.slice(5)}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[15px] text-ink-2">Nothing needs you this week.</p>
      )}
      {open.length > shown.length && (
        <button type="button" className="mt-4 font-mono text-[11px] tracking-[0.1em] text-ink-2 uppercase hover:text-ink" onClick={() => setAll(true)}>
          {open.length - shown.length} more
        </button>
      )}
    </div>
  );
}
