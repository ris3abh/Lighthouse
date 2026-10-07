import { ArrowRight, ArrowUp, Plus, Sparkles, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type AgentRunView, type AgentStatus, type ConversationView, type RuleCheck } from "../api";
import { useRefresh } from "../App";
import { countTokens, fmtTokens, fmtUsd, type Item, useRunStream } from "../runStream";
import Markdown from "./Markdown";
import RuleCheckView from "./RuleCheck";
import ToolCall from "./ToolCall";
import { Button, useToast } from "./ui";

const CONV_KEY = "lh-chat-conv";
const SUGGESTIONS = ["Where do I stand, and what are the 3 things to do this week?", "Find hackathons I could judge in the next two months",
  "Which criteria are closest to banked?"]; // prettier-ignore

type Turn = { role: "user" | "assistant"; text: string; runId?: string | null; items?: Item[]; meta?: string; check?: RuleCheck | null };

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
      { role: "assistant", text: run.text, runId: run.id, items: undefined, meta: meta(run), check: run.rule_check },
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
      className="fixed inset-0 z-40 flex animate-slide-in flex-col border-l border-frame bg-surface md:static md:inset-auto md:z-auto md:w-[440px] md:shrink-0"
    >
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-frame px-4 lg:h-16">
        <Sparkles className="size-[18px]" strokeWidth={1.5} aria-hidden />
        <span className="display text-2xl uppercase">Ask</span>
        <select
          aria-label="Conversation"
          className="input ml-auto h-8 w-44 py-0 font-mono text-[11px]"
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
        <Button size="sm" variant="ghost" className="px-2" onClick={newChat} title="New conversation" aria-label="New conversation">
          <Plus />
        </Button>
        <Button size="sm" variant="ghost" className="px-2" onClick={onClose} aria-label="Close chat">
          <X />
        </Button>
      </header>

      {status && !status.available && (
        <div className="border-b border-alert bg-alert-soft px-4 py-3 text-xs text-ink">
          <span className="eyebrow mr-2 text-alert">Unavailable</span>
          {status.reason}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        {turns.length === 0 && !runId && (
          <div>
            <p className="display text-4xl">What do you want to know?</p>
            <p className="mt-3 text-sm leading-relaxed text-ink-2">
              The agent reads your workspace and the web, and <strong className="font-semibold text-ink">proposes</strong> changes to your
              Inbox. It never changes anything on its own.
            </p>
            <div className="mt-6 border-t border-line">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="group flex w-full items-center gap-3 border-b border-line py-3 text-left text-sm text-ink-2 hover:text-ink"
                >
                  <span className="min-w-0 flex-1">{s}</span>
                  <ArrowRight className="size-4 shrink-0 transition-transform group-hover:translate-x-1" aria-hidden />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-col gap-6">
          {turns.map((t, i) => (
            <TurnView key={i} t={t} />
          ))}
          {runId && <TurnView t={{ role: "assistant", text: "", items: live.items, meta: live.tokens ? `${fmtTokens(live.tokens)} tokens so far` : "thinking" }} streaming />}
          {live.error && <p className="text-xs text-alert">{live.error}</p>}
        </div>
        <div ref={bottom} />
      </div>

      <form
        className="border-t border-frame p-4"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <div className="flex items-end gap-2 border border-ink bg-surface focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink">
          <textarea
            className="min-h-14 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm text-ink placeholder:text-muted focus:outline-none"
            placeholder={runId ? "Working…" : "Ask about your case"}
            aria-label="Message"
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
          {runId ? (
            <Button size="sm" variant="secondary" type="button" className="m-1.5" onClick={() => runId && api.stopRun(runId)}>
              <Square className="fill-current" />
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="primary" type="submit" className="m-1.5 px-2.5" aria-label="Send" disabled={!input.trim() || sending || status?.available === false}>
              <ArrowUp />
            </Button>
          )}
        </div>
        <p className="mt-2 truncate font-mono text-[10.5px] text-muted">
          {status && `${status.model} · ${fmtTokens(status.month.tokens)} TOKENS · ${fmtUsd(status.month.usd)}${status.budget.monthly_usd ? ` OF $${status.budget.monthly_usd}` : ""} THIS MONTH`}
          {" · ENTER TO SEND"}
        </p>
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
    return <div className="ml-10 animate-rise self-end bg-ink px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-on-ink">{t.text}</div>;
  const items = t.items;
  return (
    <div className="animate-rise border-l border-ink pl-4">
      {items && items.length > 0 ? (
        <div className="flex flex-col gap-2">
          {items.map((it, i) =>
            it.kind === "tool" ? (
              <ToolCall key={i} t={it.tool} />
            ) : it.kind === "error" ? (
              <p key={i} className="text-xs text-alert">
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
      {streaming && (!items || items.length === 0) && <span className="inline-block size-2 animate-tool-pulse bg-ink" aria-label="Thinking" />}
      <RuleCheckView check={t.check} compact />
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10.5px] text-muted uppercase">
        {t.meta && <span>{t.meta}</span>}
        {t.runId && (
          <a href={`#/agent?run=${t.runId}`} className="inline-flex items-center gap-1 hover:text-ink">
            Run details <ArrowRight className="size-3" aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}
