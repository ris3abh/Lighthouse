import { useEffect, useState } from "react";
import { api, type AgentRunView, type Candidate } from "../api";
import { useRefresh } from "../App";
import Markdown from "../components/Markdown";
import ToolCall from "../components/ToolCall";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";
import { cacheRate, countTokens, fmtPct, fmtTokens, fmtUsd, itemsFromTimeline, useRunStream } from "../runStream";

const KIND_LABEL = { chat: "chat", manual: "manual", scheduled: "scheduled" } as const;
const STATUS_TONE: Record<string, string> = {
  running: "text-amber-600",
  done: "text-emerald-600",
  error: "text-red-600",
  stopped: "text-zinc-500",
};

function duration(r: AgentRunView) {
  if (!r.finished_at) return "running";
  const s = Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function Agent({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => Promise.all([api.runs(), api.agentStatus()]), [version]);
  const [kind, setKind] = useState<"all" | "chat" | "manual" | "scheduled">("all");
  const [selected, setSelected] = useState<string | null>(focus);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (focus) setSelected(focus);
  }, [focus]);

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const [runs, status] = data.data;
  const shown = runs.filter((r) => kind === "all" || r.kind === kind);
  const current = selected ?? shown[0]?.id ?? null;

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
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Agent"
        subtitle="Every agent run, from chat, by hand or on a schedule: what it read, what it proposed, what it cost."
      />

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Card className="p-4 md:col-span-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (prompt.trim()) start();
            }}
          >
            <label className="label" htmlFor="agent-task">
              Run a task
            </label>
            <div className="flex gap-2">
              <input
                id="agent-task"
                className="input"
                placeholder="e.g. Find peer-review calls for ML workshops closing in the next 6 weeks"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={!status.available}
              />
              <Button type="submit" variant="primary" disabled={!prompt.trim() || busy || !status.available}>
                Run
              </Button>
            </div>
            <p className="mt-1.5 text-xs text-zinc-500">
              {status.available
                ? `chat ${status.models.chat} · tasks ${status.models.task} · missions ${status.models.mission} · effort ${status.effort} · web search ${status.web_search ? "on" : "off"}`
                : `Unavailable: ${status.reason}`}
            </p>
          </form>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium text-zinc-500">This month</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{fmtUsd(status.month.usd)}</p>
          <p className="text-xs text-zinc-500">
            {fmtTokens(status.month.tokens)} of {fmtTokens(b.monthly_tokens)} tokens
            {b.monthly_usd ? ` · cap $${b.monthly_usd}` : ""}
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-full rounded-full bg-amber-500"
              style={{ width: `${Math.min(100, (100 * status.month.tokens) / b.monthly_tokens)}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-zinc-500">
            Prompt cache: {fmtPct(status.month.cache_hit_rate)} of input tokens served from cache ({fmtTokens(status.month.cache_read)} cached,{" "}
            {fmtTokens(status.month.cache_write)} written, {fmtTokens(status.month.uncached_input)} uncached)
          </p>
          <p className="mt-1 text-[11px] text-zinc-400">
            Per run: {fmtTokens(b.per_run_tokens)} tokens{b.per_run_usd ? `, $${b.per_run_usd}` : ""} · set in lighthouse.yaml
          </p>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <Card
          title="Runs"
          actions={
            <select aria-label="Filter runs" className="input w-auto py-1 text-xs" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="all">All</option>
              <option value="chat">Chat</option>
              <option value="manual">Manual</option>
              <option value="scheduled">Scheduled</option>
            </select>
          }
        >
          {shown.length ? (
            <ul className="max-h-[70vh] divide-y divide-zinc-100 overflow-y-auto dark:divide-zinc-800">
              {shown.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelected(r.id);
                      window.location.hash = `#/agent?run=${r.id}`;
                    }}
                    className={cx("w-full px-3 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50", current === r.id && "bg-zinc-100 dark:bg-zinc-800")}
                  >
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <Chip>{KIND_LABEL[r.kind]}</Chip>
                      <span className={cx("font-medium", STATUS_TONE[r.status])}>{r.status}</span>
                      <span className="ml-auto text-zinc-400 tabular-nums">{new Date(r.started_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                    </div>
                    <p className="mt-0.5 truncate text-sm">{r.prompt}</p>
                    <p className="text-[11px] text-zinc-500 tabular-nums">
                      {r.tool_calls ?? 0} tool call{r.tool_calls === 1 ? "" : "s"} · {r.sources.length} source{r.sources.length === 1 ? "" : "s"} ·{" "}
                      {r.proposals.length} proposal{r.proposals.length === 1 ? "" : "s"} · {fmtTokens(r.counted_tokens)} · {fmtPct(cacheRate(r.usage))} cached ·{" "}
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
    <div className="flex flex-col gap-4">
      <Card
        title={
          <span className="flex items-center gap-2">
            <Chip>{run.kind}</Chip>
            <span className={cx(STATUS_TONE[live ? "running" : run.status])}>{live ? "running" : run.status}</span>
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
        <div className="px-4 py-3">
          <p className="text-sm font-medium">{run.prompt}</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-5">
            <div>
              <dt className="text-zinc-500">Cost</dt>
              <dd className="font-medium tabular-nums">{fmtUsd(run.cost_usd)}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Tokens (counted)</dt>
              <dd className="font-medium tabular-nums">{fmtTokens(tokens)}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Input: cached / written / uncached</dt>
              <dd className="tabular-nums" title="Cached = read from the prompt cache (system prompt, tools, earlier turns); written = added to the cache this run; uncached = billed at the full rate">
                {fmtTokens(run.usage.cache_read_input_tokens)} / {fmtTokens(run.usage.cache_creation_input_tokens)} /{" "}
                {fmtTokens(run.usage.input_tokens)}{" "}
                <span className="text-zinc-400">({fmtPct(cacheRate(run.usage))} cached)</span>
              </dd>
            </div>
            <div>
              <dt className="text-zinc-500">Output</dt>
              <dd className="tabular-nums">{fmtTokens(run.usage.output_tokens)}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Duration</dt>
              <dd className="tabular-nums">{duration(run)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-[11px] text-zinc-400">
            {run.engine} · {run.model}
            {run.stop_reason && ` · ${run.stop_reason}`}
            {run.conversation_id && " · from chat"}
          </p>
          {run.error && <p className="mt-2 text-xs text-red-600">{run.error}</p>}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
        <Card title="What it did">
          <div className="flex flex-col gap-1.5 p-3">
            {items.length ? (
              items.map((it, i) =>
                it.kind === "tool" ? (
                  <ToolCall key={i} t={it.tool} />
                ) : it.kind === "error" ? (
                  <p key={i} className="text-xs text-red-600">
                    {it.text}
                  </p>
                ) : (
                  <Markdown key={i} text={it.text} />
                ),
              )
            ) : (
              <Empty>{live ? "Starting…" : "Nothing recorded."}</Empty>
            )}
            {stream.error && <p className="text-xs text-red-600">{stream.error}</p>}
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <Card title={`Sources read (${run.sources.length})`}>
            {run.sources.length ? (
              <ul className="divide-y divide-zinc-100 text-xs dark:divide-zinc-800">
                {run.sources.map((s, i) => (
                  <li key={i} className="px-3 py-2">
                    <a href={s.url} target="_blank" rel="noreferrer" className="link break-all">
                      {s.title || s.url}
                    </a>
                    {s.observation_id && <p className="mt-0.5 font-mono text-[10px] text-zinc-400">snapshot {s.observation_id}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No pages read.</Empty>
            )}
          </Card>
          <Card title={`Proposals (${run.proposals.length})`}>
            {run.proposals.length ? (
              <ul className="divide-y divide-zinc-100 text-xs dark:divide-zinc-800">
                {run.proposals.map((id) => {
                  const c = byId.get(id);
                  return (
                    <li key={id} className="px-3 py-2">
                      <a href="#/inbox" className="link">
                        {c?.title ?? id}
                      </a>
                      <p className="mt-0.5 text-[11px] text-zinc-500">
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
              <ul className="divide-y divide-zinc-100 text-xs dark:divide-zinc-800">
                {changes.map((ch) => (
                  <li key={ch.id} className={cx("px-3 py-2", ch.undone && "opacity-60")}>
                    <div className="flex items-start gap-1.5">
                      <span className="min-w-0 flex-1">
                        {ch.auto && <Chip tone="amber">auto</Chip>} <span className="font-mono text-[11px]">{ch.action}</span> {ch.summary}
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
                    <p className="text-[11px] text-zinc-400">
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
