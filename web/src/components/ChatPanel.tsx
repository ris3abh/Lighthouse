import { useEffect, useRef, useState } from "react";
import { api, type AgentRunView, type AgentStatus, type ConversationView } from "../api";
import { useRefresh } from "../App";
import { countTokens, fmtTokens, fmtUsd, type Item, useRunStream } from "../runStream";
import Markdown from "./Markdown";
import ToolCall from "./ToolCall";
import { Button, cx, useToast } from "./ui";

const CONV_KEY = "lh-chat-conv";
const SUGGESTIONS = ["Where do I stand, and what are the 3 things to do this week?", "Find hackathons I could judge in the next two months",
  "Which criteria are closest to banked?"]; // prettier-ignore

type Turn = { role: "user" | "assistant"; text: string; runId?: string | null; items?: Item[]; meta?: string };

function store(key: string, value: string | null) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
}
function load(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export default function ChatPanel({ page, onClose }: { page: string; onClose: () => void }) {
  const { bump } = useRefresh();
  const toast = useToast();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [convs, setConvs] = useState<{ id: string; title: string }[]>([]);
  const [convId, setConvId] = useState<string | null>(() => load(CONV_KEY));
  const [turns, setTurns] = useState<Turn[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const live = useRunStream(runId, (run: AgentRunView) => {
    setTurns((t) => [
      ...t,
      { role: "assistant", text: run.text, runId: run.id, items: undefined, meta: meta(run) },
    ]);
    setRunId(null);
    bump(); // proposals may have changed the Inbox badge
    api.agentStatus().then(setStatus).catch(() => undefined);
  });

  useEffect(() => {
    api.agentStatus().then(setStatus).catch(() => setStatus(null));
    api.conversations().then(setConvs).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!convId) {
      setTurns([]);
      return;
    }
    api
      .conversation(convId)
      .then((c: ConversationView) => setTurns(c.messages.map((m) => ({ role: m.role, text: m.text, runId: m.run_id }))))
      .catch(() => {
        setConvId(null);
        store(CONV_KEY, null);
      });
  }, [convId]);

  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from scrollIntoView, and an effect must not return one.
    void bottom.current?.scrollIntoView({ block: "end" });
  }, [turns, live.items]);

  // Keep the finished turn's tool calls visible: when the run ends, attach the live items to it.
  const liveItems = useRef<Item[]>([]);
  liveItems.current = live.items;
  useEffect(() => {
    if (!runId && liveItems.current.length)
      setTurns((t) => {
        const last = t[t.length - 1];
        if (last?.role === "assistant" && !last.items) return [...t.slice(0, -1), { ...last, items: liveItems.current }];
        return t;
      });
  }, [runId]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending || runId) return;
    setSending(true);
    try {
      const r = await api.chat(message, convId, page);
      if (r.conversation_id !== convId) {
        setConvId(r.conversation_id);
        store(CONV_KEY, r.conversation_id);
        api.conversations().then(setConvs).catch(() => undefined);
      }
      setTurns((t) => [...t, { role: "user", text: message }]);
      setRunId(r.run_id);
      setInput("");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSending(false);
    }
  };

  const newChat = () => {
    setConvId(null);
    store(CONV_KEY, null);
    setTurns([]);
  };

  return (
    <aside
      aria-label="Chat with the Lighthouse agent"
      className="fixed inset-0 z-40 flex flex-col border-l border-zinc-200 bg-white md:static md:inset-auto md:z-auto md:w-[420px] md:shrink-0 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <header className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <span className="text-sm font-semibold">Ask Lighthouse</span>
        <select
          aria-label="Conversation"
          className="input ml-auto w-40 py-1 text-xs"
          value={convId ?? ""}
          onChange={(e) => {
            const id = e.target.value || null;
            setConvId(id);
            store(CONV_KEY, id);
          }}
        >
          <option value="">New conversation</option>
          {convs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title || c.id}
            </option>
          ))}
        </select>
        <Button size="sm" variant="ghost" onClick={newChat} title="New conversation">
          ＋
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close chat">
          ✕
        </Button>
      </header>

      {status && !status.available && (
        <div className="border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          The agent isn't available: {status.reason}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {turns.length === 0 && !runId && (
          <div className="text-sm text-zinc-500">
            <p className="mb-2">
              Ask about your case. The agent reads your workspace and the web, and can <strong>propose</strong> changes to your
              Inbox. It never changes anything itself.
            </p>
            <div className="flex flex-col gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} className="rounded-md border border-zinc-200 px-2 py-1.5 text-left text-xs hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-col gap-3">
          {turns.map((t, i) => (
            <TurnView key={i} t={t} />
          ))}
          {runId && <TurnView t={{ role: "assistant", text: "", items: live.items, meta: live.tokens ? `${fmtTokens(live.tokens)} tokens so far` : "thinking…" }} streaming />}
          {live.error && <p className="text-xs text-red-600">{live.error}</p>}
        </div>
        <div ref={bottom} />
      </div>

      <form
        className="border-t border-zinc-200 p-2 dark:border-zinc-800"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          className="input min-h-16 resize-none text-sm"
          placeholder={runId ? "Working…" : "Ask anything about your case (Enter to send, Shift+Enter for a new line)"}
          value={input}
          disabled={!!runId || status?.available === false}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <div className="mt-1.5 flex items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-[11px] text-zinc-400">
            {status && `${status.model} · this month ${fmtTokens(status.month.tokens)} tokens, ${fmtUsd(status.month.usd)}${status.budget.monthly_usd ? ` of $${status.budget.monthly_usd}` : ""}`}
          </span>
          {runId ? (
            <Button size="sm" variant="danger" type="button" onClick={() => runId && api.stopRun(runId)}>
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="primary" type="submit" disabled={!input.trim() || sending || status?.available === false}>
              Send
            </Button>
          )}
        </div>
      </form>
    </aside>
  );
}

function meta(run: AgentRunView) {
  const parts = [`${fmtTokens(run.counted_tokens ?? countTokens(run.usage))} tokens`, fmtUsd(run.cost_usd)];
  if (run.status !== "done") parts.unshift(run.status === "stopped" ? `stopped (${run.stop_reason})` : `error: ${run.error}`);
  if (run.proposals.length) parts.push(`${run.proposals.length} proposal${run.proposals.length > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

function TurnView({ t, streaming }: { t: Turn; streaming?: boolean }) {
  if (t.role === "user")
    return <div className="ml-8 self-end rounded-lg bg-zinc-900 px-3 py-2 text-sm whitespace-pre-wrap text-white dark:bg-zinc-100 dark:text-zinc-900">{t.text}</div>;
  const items = t.items;
  return (
    <div className="mr-4">
      {items && items.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {items.map((it, i) =>
            it.kind === "tool" ? (
              <ToolCall key={i} t={it.tool} />
            ) : it.kind === "error" ? (
              <p key={i} className="text-xs text-red-600">
                {it.text}
              </p>
            ) : (
              <Markdown key={i} text={it.text} />
            ),
          )}
        </div>
      ) : (
        t.text && <Markdown text={t.text} />
      )}
      {streaming && (!items || items.length === 0) && <span className="inline-block animate-pulse text-zinc-400">●</span>}
      <div className={cx("mt-1 flex gap-2 text-[11px] text-zinc-400")}>
        {t.meta && <span>{t.meta}</span>}
        {t.runId && (
          <a href={`#/agent?run=${t.runId}`} className="hover:text-zinc-700 dark:hover:text-zinc-200">
            run details →
          </a>
        )}
      </div>
    </div>
  );
}
