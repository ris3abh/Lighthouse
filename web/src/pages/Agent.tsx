import { useEffect, useState } from "react";
import { api, type AgentRunView, type AgentStatus, type Candidate } from "../api";
import { useRefresh } from "../App";
import Markdown from "../components/Markdown";
import RuleCheckView from "../components/RuleCheck";
import ToolCall from "../components/ToolCall";
import { Play } from "lucide-react";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, Progress, useToast } from "../components/ui";
import { useLoad } from "../hooks";
import { cacheRate, countTokens, fmtPct, fmtTokens, fmtUsd, itemsFromTimeline, useRunStream } from "../runStream";

const KIND_LABEL = { chat: "chat", manual: "manual", scheduled: "scheduled" } as const;
const STATUS_TONE: Record<string, string> = {
  running: "text-ink",
  done: "text-ink",
  error: "text-alert",
  stopped: "text-muted",
};

function duration(r: AgentRunView) {
  if (!r.finished_at) return "running";
  const s = Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function Agent({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => Promise.all([api.runs(), api.agentStatus(), api.missions(), api.refusals()]), [version]);
  const [kind, setKind] = useState<"all" | "chat" | "manual" | "scheduled">("all");
  const [selected, setSelected] = useState<string | null>(focus);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (focus) setSelected(focus);
  }, [focus]);

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const [runs, status, missionList, refused] = data.data;
  const runMission = async (name: string) => {
    try {
      const r = await api.runMission(name);
      setSelected(r.run_id);
      window.location.hash = `#/agent?run=${r.run_id}`;
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const shown = runs.filter((r) => kind === "all" || r.kind === kind);
  const current = selected || shown[0]?.id || null;

  const start = async () => {
    setBusy(true);
    try {
      const r = await api.startRun(prompt);
      setPrompt("");
      setSelected(r.run_id);
      window.location.hash = `#/agent?run=${r.run_id}`;
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const b = status.budget;
  const monthPct = b.monthly_tokens ? Math.min(100, (100 * status.month.tokens) / b.monthly_tokens) : 0;
  return (
    <div>
      <PageHeader
        eyebrow={plural(runs.length, "run")}
        title="Agent"
        subtitle="Every agent run, from chat, by hand or on a schedule: what it read, what it proposed, what it cost."
      />

      <section className="card mb-8 grid animate-rise @4xl:grid-cols-[2fr_1fr]">
        <form
          className="border-b border-line p-6 @4xl:border-r @4xl:border-b-0 md:p-8"
          onSubmit={(e) => {
            e.preventDefault();
            if (prompt.trim()) start();
          }}
        >
          <label className="label" htmlFor="agent-task">
            Run a task
          </label>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <input
              id="agent-task"
              className="input h-12 text-base"
              placeholder="Find peer-review calls for ML workshops closing in the next 6 weeks"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={!status.available}
            />
            <Button type="submit" variant="primary" className="h-12 px-6" disabled={!prompt.trim() || busy || !status.available}>
              <Play /> Run
            </Button>
          </div>
          <p className={cx("mt-4 font-mono text-[11px] leading-relaxed uppercase", status.available ? "text-muted" : "text-alert")}>
            {status.available
              ? `${tiers(status)} · effort ${status.effort} · web search ${status.web_search ? "on" : "off"}${status.cheap_mode ? " · cheap mode" : ""}`
              : `Unavailable: ${status.reason}`}
          </p>
        </form>
        <div className="p-6 md:p-8">
          <p className="eyebrow">This month</p>
          <p className="display mt-3 text-6xl">{fmtUsd(status.month.usd)}</p>
          <p className="mt-2 font-mono text-xs text-ink-2">
            {fmtTokens(status.month.tokens)} / {fmtTokens(b.monthly_tokens)} TOKENS{b.monthly_usd ? ` · CAP $${b.monthly_usd}` : ""}
          </p>
          <div className="mt-4">
            <Progress value={monthPct} max={100} alert={monthPct >= 90} label="Monthly token budget used" />
          </div>
          <p className="mt-4 text-xs leading-relaxed text-ink-2">
            Prompt cache served {fmtPct(status.month.cache_hit_rate)} of input ({fmtTokens(status.month.cache_read)} cached, {fmtTokens(status.month.cache_write)}{" "}
            written, {fmtTokens(status.month.uncached_input)} uncached). Per run: {fmtTokens(b.per_run_tokens)} tokens
            {b.per_run_usd ? `, $${b.per_run_usd}` : ""}.
          </p>
        </div>
      </section>

      <Card title="Missions" className="mb-8">
        <ul className="grid divide-y divide-line @3xl:grid-cols-2 @3xl:divide-x @3xl:divide-y-0">
          {missionList.map((m) => (
            <li key={m.name} className="flex items-start gap-4 p-6">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-3">
                  <span className="display text-3xl">{m.title}</span> <Chip tone={m.enabled ? "ink" : "muted"}>{m.enabled ? "on" : "off"}</Chip>
                </p>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">
                  {m.name === "opportunity_scout"
                    ? "Weekly: finds judging calls, CFPs, awards and memberships for your weakest criteria."
                    : "Daily: what changed and the three things to do this week. Skipped (no cost) when nothing changed."}
                </p>
                <p className="mt-3 font-mono text-[10.5px] text-muted uppercase">
                  {m.enabled && m.next_run ? `Next ${new Date(m.next_run).toLocaleString()} · ` : m.enabled ? "" : "Turn on in Settings · "}
                  {m.model}
                  {m.last_run && (
                    <>
                      {" · last "}
                      <a className="link" href={`#/agent?run=${m.last_run.id}`}>
                        {new Date(m.last_run.at).toLocaleDateString()}
                      </a>
                      {`, ${plural(m.last_run.proposals, "proposal")}, ${fmtUsd(m.last_run.cost_usd)}`}
                    </>
                  )}
                </p>
              </div>
              <Button size="sm" disabled={!status.available} onClick={() => runMission(m.name)}>
                Run now
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title={
          <span className="flex items-center gap-3">
            Declined <span className="num text-ink-2">{refused.length}</span>
          </span>
        }
        className="mb-8"
        actions={<span className="font-mono text-[10.5px] text-muted uppercase">What the agent and its guardrails refused</span>}
      >
        {refused.length ? (
          <ul className="max-h-80 overflow-y-auto">
            {refused.slice(0, 50).map((r, i) => (
              <li key={i} className="grid gap-1 border-b border-line px-5 py-3 last:border-b-0 @3xl:grid-cols-[180px_minmax(0,1fr)] @3xl:gap-6">
                <div className="font-mono text-[10.5px] text-muted uppercase">
                  <p className="text-alert">{r.rule.replace(/_/g, " ")}</p>
                  <p>{new Date(r.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</p>
                </div>
                <div className="min-w-0 text-sm">
                  <p className="text-ink">{r.message}</p>
                  {r.alternative && <p className="mt-0.5 text-ink-2">{r.alternative}</p>}
                  {r.detail && <p className="mt-1 truncate font-mono text-[11px] text-muted" title={r.detail}>{r.detail}</p>}
                  {r.run_id && (
                    <a className="link mt-1 inline-block font-mono text-[10.5px] uppercase" href={`#/agent?run=${r.run_id}`}>
                      Run details
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Nothing declined yet.</Empty>
        )}
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @5xl:grid-cols-[400px_minmax(0,1fr)]">
        <Card
          title="Runs"
          className="self-start"
          actions={
            <select aria-label="Filter runs" className="input h-8 w-auto py-0 font-mono text-[11px]" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="all">All</option>
              <option value="chat">Chat</option>
              <option value="manual">Manual</option>
              <option value="scheduled">Scheduled</option>
            </select>
          }
        >
          {shown.length ? (
            <ul className="max-h-[75vh] overflow-y-auto">
              {shown.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelected(r.id);
                      window.location.hash = `#/agent?run=${r.id}`;
                    }}
                    className={cx("w-full border-b border-l-[3px] border-b-line px-5 py-4 text-left transition-colors hover:bg-sunken", current === r.id ? "border-l-ink bg-sunken" : "border-l-transparent")}
                  >
                    <div className="flex items-center gap-2 text-[11px]">
                      <Chip>{r.mission ? (missionList.find((m) => m.name === r.mission)?.title ?? r.mission) : KIND_LABEL[r.kind]}</Chip>
                      <span className={cx("font-mono text-[11px] uppercase", STATUS_TONE[r.status])}>{r.status}</span>
                      <span className="num ml-auto text-muted">{new Date(r.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                    </div>
                    <p className="mt-2 truncate text-[15px]">{r.prompt}</p>
                    <p className="num mt-1 text-[10.5px] text-muted">
                      {r.tool_calls ?? 0} tool call{r.tool_calls === 1 ? "" : "s"} · {r.sources.length} source{r.sources.length === 1 ? "" : "s"} ·{" "}
                      {r.proposals.length} proposal{r.proposals.length === 1 ? "" : "s"} · {fmtTokens(r.counted_tokens)} · {fmtPct(cacheRate(r.usage))} cached ·{" "}
                      {r.tier ? `${r.tier} · ${r.model} · ` : ""}
                      {fmtUsd(r.cost_usd)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No runs yet. Ask something in the chat panel or run a task above.</Empty>
          )}
        </Card>

        {current ? <RunDetail key={current} runId={current} onChanged={bump} /> : <Card><Empty>Select a run.</Empty></Card>}
      </div>
    </div>
  );
}

function RunDetail({ runId, onChanged }: { runId: string; onChanged: () => void }) {
  const toast = useToast();
  const stored = useLoad(() => Promise.all([api.run(runId), api.allCandidates(), api.changes(`agent:${runId}`)]), [runId]);
  const [live, setLive] = useState(false);
  const stream = useRunStream(live ? runId : null, () => {
    setLive(false);
    stored.reload();
    onChanged();
  });

  useEffect(() => {
    if (stored.data?.[0].status === "running") setLive(true);
  }, [stored.data]);

  if (stored.error) return <ErrorBox error={stored.error} retry={stored.reload} />;
  if (!stored.data) return <Loading />;
  const [run, candidates, changes] = stored.data;
  const byId = new Map<string, Candidate>(candidates.map((c) => [c.id, c]));
  const items = live ? stream.items : itemsFromTimeline(run.timeline);
  const tokens = live ? stream.tokens : countTokens(run.usage);

  return (
    <div className="@container flex min-w-0 flex-col gap-8">
      <Card
        title={
          <span className="flex items-center gap-2">
            <Chip>{run.kind}</Chip>
            <span className={cx("uppercase", STATUS_TONE[live ? "running" : run.status])}>{live ? "running" : run.status}</span>
          </span>
        }
        actions={
          live ? (
            <Button size="sm" variant="danger" onClick={() => api.stopRun(runId).then(() => toast("Stopping…"))}>
              Stop
            </Button>
          ) : undefined
        }
      >
        <div className="px-6 py-6">
          <p className="display text-3xl md:text-4xl">{run.prompt}</p>
          <dl className="mt-6 grid grid-cols-2 gap-px border border-line bg-line text-xs @2xl:grid-cols-5 [&>div]:bg-surface [&>div]:p-3 [&_dd]:mt-1 [&_dd]:font-mono [&_dd]:text-sm [&_dt]:eyebrow">
            <div>
              <dt>Cost</dt>
              <dd>{fmtUsd(run.cost_usd)}</dd>
            </div>
            <div>
              <dt>Tokens (counted)</dt>
              <dd>{fmtTokens(tokens)}</dd>
            </div>
            <div>
              <dt>Input</dt>
              <dd title="Cached = read from the prompt cache (system prompt, tools, earlier turns); written = added to the cache this run; uncached = billed at the full rate">
                {fmtTokens(run.usage.cache_read_input_tokens + run.usage.cache_creation_input_tokens + run.usage.input_tokens)}{" "}
                <span className="text-muted">({fmtPct(cacheRate(run.usage))} cached)</span>
              </dd>
            </div>
            <div>
              <dt>Output</dt>
              <dd>{fmtTokens(run.usage.output_tokens)}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{duration(run)}</dd>
            </div>
          </dl>
          <p className="mt-4 font-mono text-[10.5px] text-muted uppercase">
            {run.provider ?? run.engine} · {run.tier ? `${run.tier} tier · ` : ""}
            {run.model}
            {run.task && run.task !== run.kind && ` · ${run.task.replace(/_/g, " ")}`}
            {run.stop_reason && ` · ${run.stop_reason}`}
            {run.conversation_id && " · from chat"}
          </p>
          {run.error && <p className="mt-2 text-xs text-alert">{run.error}</p>}
        </div>
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @4xl:grid-cols-[minmax(0,1fr)_300px]">
        <Card title="What it did">
          <div className="flex flex-col gap-2 p-5">
            {items.length ? (
              items.map((it, i) =>
                it.kind === "tool" ? (
                  <ToolCall key={i} t={it.tool} />
                ) : it.kind === "error" ? (
                  <p key={i} className="text-xs text-alert">
                    {it.text}
                  </p>
                ) : (
                  <Markdown key={i} text={it.text} />
                ),
              )
            ) : (
              <Empty>{live ? "Starting…" : "Nothing recorded."}</Empty>
            )}
            {stream.error && <p className="text-xs text-alert">{stream.error}</p>}
          </div>
        </Card>

        <div className="flex flex-col gap-8">
          {run.rule_check && run.rule_check.claims.length > 0 && (
            <div>
              <RuleCheckView
                check={run.rule_check}
                onRecheck={() =>
                  api
                    .recheckRun(run.id)
                    .then(() => stored.reload())
                    .catch((e: Error) => toast(e.message, "error"))
                }
              />
            </div>
          )}
          <Card title={`Sources read (${run.sources.length})`}>
            {run.sources.length ? (
              <ul className="divide-y divide-line text-xs">
                {run.sources.map((s, i) => (
                  <li key={i} className="px-5 py-3">
                    <a href={s.url} target="_blank" rel="noreferrer" className="link break-all">
                      {s.title || s.url}
                    </a>
                    {s.observation_id && <p className="mt-0.5 font-mono text-[10px] text-muted">snapshot {s.observation_id}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No pages read.</Empty>
            )}
          </Card>
          <Card title={`Proposals (${run.proposals.length})`}>
            {run.proposals.length ? (
              <ul className="divide-y divide-line text-xs">
                {run.proposals.map((id) => {
                  const c = byId.get(id);
                  return (
                    <li key={id} className="px-5 py-3">
                      <a href="#/inbox" className="link">
                        {c?.title ?? id}
                      </a>
                      <p className="mt-0.5 text-[11px] text-muted">
                        {c ? `${c.kind} · ${c.status}` : "accepted or removed from the Inbox"}
                      </p>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Empty>No proposals.</Empty>
            )}
          </Card>
          <Card title={`Changes (${changes.length})`}>
            {changes.length ? (
              <ul className="divide-y divide-line text-xs">
                {changes.map((ch) => (
                  <li key={ch.id} className={cx("px-5 py-3", ch.undone && "opacity-50")}>
                    <div className="flex items-start gap-1.5">
                      <span className="min-w-0 flex-1">
                        {ch.auto && <Chip tone="outline">auto</Chip>} <span className="font-mono text-[11px]">{ch.action}</span> {ch.summary}
                      </span>
                      {ch.undoable && !ch.undone && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            api
                              .undoChange(ch.id)
                              .then(() => {
                                toast("Undone");
                                stored.reload();
                                onChanged();
                              })
                              .catch((e: Error) => toast(e.message, "error"))
                          }
                        >
                          Undo
                        </Button>
                      )}
                    </div>
                    <p className="text-[11px] text-muted">
                      {new Date(ch.at).toLocaleString()}
                      {ch.undone && " · undone"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No workspace changes.</Empty>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

/** "hard claude-opus-5-5 · mid claude-sonnet-5-5 · mundane gpt-5-mini (OpenAI)": the three tiers (ADR 0009). */
function tiers(status: AgentStatus): string {
  const by = (tier: string) => status.routes.find((r) => r.tier === tier);
  return (["hard", "mid", "mundane"] as const)
    .map((tier) => {
      const r = by(tier);
      return r ? `${tier} ${r.model}${r.provider === "openai" ? " (OpenAI)" : ""}` : "";
    })
    .filter(Boolean)
    .join(" · ");
}
