import { useEffect, useRef, useState } from "react";
import { api, type AgentEvent, type AgentRunView, type TimelineItem } from "./api";
import type { ToolView } from "./components/ToolCall";

export type Item = { kind: "text"; text: string } | { kind: "tool"; tool: ToolView } | { kind: "error"; text: string };

export type LiveRun = { items: Item[]; done: AgentRunView | null; tokens: number; error: string | null };

/** Turn a stored run's timeline into display items. */
export function itemsFromTimeline(timeline: TimelineItem[] = []): Item[] {
  return timeline.map((t) =>
    t.type === "tool_call"
      ? { kind: "tool", tool: { id: t.tool_id ?? "", name: t.tool ?? "", input: t.input, ok: t.ok, summary: t.result } }
      : t.type === "error"
        ? { kind: "error", text: t.text }
        : { kind: "text", text: t.text },
  );
}

/** Subscribe to a run's SSE stream (replays from the start), folding events into display items. */
export function useRunStream(runId: string | null, onDone?: (run: AgentRunView) => void): LiveRun {
  const [state, setState] = useState<LiveRun>({ items: [], done: null, tokens: 0, error: null });
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (!runId) return;
    setState({ items: [], done: null, tokens: 0, error: null });
    let streamingText = false; // true while text deltas are filling the last text item
    const es = new EventSource(api.runStreamUrl(runId));
    const update = (fn: (s: LiveRun) => LiveRun) => setState((s) => fn(s));
    es.onmessage = () => undefined;
    const on = (type: string, fn: (e: AgentEvent) => void) =>
      es.addEventListener(type, (m) => fn(JSON.parse((m as MessageEvent).data) as AgentEvent));

    on("text_delta", (e) =>
      update((s) => {
        const items = [...s.items];
        const last = items[items.length - 1];
        if (streamingText && last?.kind === "text") items[items.length - 1] = { kind: "text", text: last.text + String(e.text) };
        else items.push({ kind: "text", text: String(e.text) });
        streamingText = true;
        return { ...s, items };
      }),
    );
    on("text", (e) =>
      update((s) => {
        const items = [...s.items];
        const last = items[items.length - 1];
        if (streamingText && last?.kind === "text") items[items.length - 1] = { kind: "text", text: String(e.text) };
        else items.push({ kind: "text", text: String(e.text) });
        streamingText = false;
        return { ...s, items };
      }),
    );
    on("tool_call", (e) =>
      update((s) => {
        streamingText = false;
        const tool: ToolView = { id: String(e.id), name: String(e.name), input: (e.input as Record<string, unknown>) ?? {},
          touches: e.touches as string[], read_only: e.read_only as boolean, ok: null };
        return { ...s, items: [...s.items, { kind: "tool", tool }] };
      }),
    );
    on("tool_result", (e) =>
      update((s) => ({
        ...s,
        items: s.items.map((it) =>
          it.kind === "tool" && it.tool.id === e.id
            ? { kind: "tool", tool: { ...it.tool, ok: e.ok as boolean, summary: String(e.summary ?? ""), proposals: e.proposals as string[] } }
            : it,
        ),
      })),
    );
    on("usage", (e) => update((s) => ({ ...s, tokens: ((e.usage as Record<string, number>) ? countTokens(e.usage as Record<string, number>) : s.tokens) })));
    on("agent_error", (e) => update((s) => ({ ...s, items: [...s.items, { kind: "error", text: String(e.error) }] })));
    on("done", (e) => {
      const run = e.run as AgentRunView;
      update((s) => ({ ...s, done: run, tokens: countTokens(run.usage) }));
      es.close();
      doneRef.current?.(run);
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return;
      update((s) => (s.done ? s : { ...s, error: "Lost the connection to the run. It keeps going; reopen to see the result." }));
      es.close();
    };
    return () => es.close();
  }, [runId]);

  return state;
}

export function countTokens(u: { input_tokens?: number; output_tokens?: number; cache_creation_input_tokens?: number }) {
  return (u.input_tokens ?? 0) + (u.output_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0);
}

/** Share of input tokens served from the prompt cache (system prompt + tool definitions + earlier turns). */
export function cacheRate(u: { input_tokens: number; cache_creation_input_tokens: number; cache_read_input_tokens: number }) {
  const total = u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens;
  return total ? u.cache_read_input_tokens / total : null;
}
export const fmtPct = (r: number | null) => (r === null ? "—" : `${Math.round(r * 100)}%`);

export const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));
export const fmtUsd = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n < 0.01 ? "<$0.01" : `$${n.toFixed(2)}`);
