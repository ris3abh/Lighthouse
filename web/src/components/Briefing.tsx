import { useEffect, useState } from "react";
import { api } from "../api";
import { useRefresh } from "../App";
import { useLoad } from "../hooks";
import RuleCheckView from "./RuleCheck";
import { Button, Card, Chip, cx, useToast } from "./ui";

/** The agent-written "what changed / 3 things to do this week", refreshed by the daily mission. */
export default function Briefing() {
  const { version, bump } = useRefresh();
  const toast = useToast();
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

  const refresh = async () => {
    try {
      await api.runMission("what_changed");
      toast("Refreshing the briefing…");
      brief.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

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
        <a href={`#/agent?run=${b.run_id}`} className="text-[11px] text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200">
          {new Date(b.generated_at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" })}
        </a>
      )}
      <Button size="sm" variant="ghost" disabled={!!refreshing} onClick={refresh}>
        {refreshing ? "Refreshing…" : "Refresh"}
      </Button>
    </span>
  );

  if (!b) return null;
  if (!b.generated_at)
    return (
      <Card title="This week" actions={actions}>
        <p className="p-4 text-sm text-zinc-500">
          No briefing yet. Press Refresh for one now, or turn on the daily what-changed mission in{" "}
          <a className="underline" href="#/settings">
            Settings
          </a>{" "}
          to get one every morning.
        </p>
      </Card>
    );

  return (
    <Card title="This week" actions={actions}>
      <div className="grid gap-4 p-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1.5 text-xs font-medium text-zinc-500">
            What changed{b.since ? ` since ${new Date(b.since + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}` : ""}
          </h3>
          {b.changed.length ? (
            <ul className="list-disc space-y-1 pl-4 text-sm">
              {b.changed.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-500">Nothing worth noting.</p>
          )}
        </div>
        <div>
          <h3 className="mb-1.5 text-xs font-medium text-zinc-500">Three things to do</h3>
          <ol className="space-y-2">
            {b.todos.map((t, i) => {
              const c = t.candidate;
              const open = c && c.status === "pending";
              return (
                <li key={i} className={cx("flex gap-2 text-sm", c && !open && "opacity-60")}>
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-[11px] font-semibold text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {t.link && !c ? (
                        <a className="hover:underline" href={t.link} {...(t.link.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
                          {t.title}
                        </a>
                      ) : (
                        t.title
                      )}
                    </p>
                    {t.why && <p className="text-xs text-zinc-500">{t.why}</p>}
                    {c && (
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Chip>{c.kind}</Chip>
                        {c.source_tier === "self_reported" && <Chip tone="amber">self-reported</Chip>}
                        {open ? (
                          <>
                            <Button size="sm" variant="primary" disabled={busy === c.id} onClick={() => decide(c.id, true)}>
                              Approve
                            </Button>
                            <Button size="sm" disabled={busy === c.id} onClick={() => decide(c.id, false)}>
                              Dismiss
                            </Button>
                            <a className="text-[11px] text-zinc-500 underline" href="#/inbox">
                              review in Inbox
                            </a>
                          </>
                        ) : (
                          <span className="text-[11px] text-zinc-500">{c.status === "rejected" ? "dismissed" : c.status}</span>
                        )}
                      </div>
                    )}
                    {t.candidate_id && !c && <p className="text-[11px] text-zinc-500">done</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
      {b.rule_check && b.rule_check.claims.length > 0 && (
        <div className="px-4 pb-3">
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
      <p className="border-t border-zinc-100 px-4 py-2 text-[11px] text-zinc-400 dark:border-zinc-800">
        Written by the agent from your workspace. Opinions, not legal advice.
      </p>
    </Card>
  );
}
