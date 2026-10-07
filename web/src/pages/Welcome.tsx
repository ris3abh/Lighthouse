import { ArrowLeft, ArrowRight, Check, FileText, Monitor, Moon, Pencil, RotateCw, Search, SkipForward, Sun, Upload } from "lucide-react";
import { useEffect, useLayoutEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { api, type OnboardingLookup, type OnboardingQuestion, type OnboardingView } from "../api";
import ChatImport from "../components/ChatImport";
import ChipInput from "../components/ChipInput";
import ConnectAI from "../components/ConnectAI";
import DropZone from "../components/DropZone";
import GmailConnect from "../components/GmailConnect";
import { Button, Chip, cx, Segmented, useToast } from "../components/ui";
import { useTheme, type ThemeMode } from "../hooks";
import { useReducedMotion } from "../lib/motion";
import { buildThread, initiallySeen, typingIndex, type Msg } from "../lib/thread";
import { DOTS_MS, typeDuration, typedPrefix } from "../lib/typing";
import { PRODUCT } from "../names";

/** Onboarding (ADR 0008, C15): one conversation in a window like Ask's, over the blurred dashboard. Every step is
 * a message in the same thread, so it scrolls up as it grows; each new message types in, and while Area O1 is
 * working the typing dots show. The reply controls sit where Ask's composer is. One ask at a time, the profile
 * filling in beside it, nothing guessed, no web without a Yes. */

const STEPS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "questions", label: "Your profile" },
  { id: "ai", label: "Your AI" },
  { id: "lookups", label: "Find your work" },
  { id: "chats", label: "Chat history" },
  { id: "mail", label: "Email" },
  { id: "tour", label: "Tour" },
] as const;

const THEMES: { value: ThemeMode; label: ReactNode; title: string }[] = [
  { value: "system", label: <Monitor aria-label="System" />, title: "Theme: follow the system" },
  { value: "light", label: <Sun aria-label="Light" />, title: "Theme: light" },
  { value: "dark", label: <Moon aria-label="Dark" />, title: "Theme: dark" },
];

type Run = (fn: () => Promise<OnboardingView>, working?: string) => Promise<void>;

export default function Welcome({ view, onChange }: { view: OnboardingView; onChange: (v: OnboardingView) => void }) {
  const toast = useToast();
  const { mode, setMode } = useTheme();
  const [working, setWorking] = useState<string | null>(null); // what Area O1 is doing while a request runs
  const busy = working !== null;
  const step = view.state.step;
  const stepIndex = Math.max(0, STEPS.findIndex((s) => s.id === step));

  const run: Run = async (fn, what = "") => {
    setWorking(what);
    try {
      onChange(await fn());
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setWorking(null);
    }
  };

  const searching = view.state.lookups.some((l) => l.status === "searching" || l.status === "accepted");
  useEffect(() => {
    if (!searching) return;
    const id = setInterval(() => api.onboarding().then(onChange, () => {}), 2500); // web lookups run in the background
    return () => clearInterval(id);
  }, [searching, onChange]);

  const msgs = buildThread(view);
  const [, typed] = useReducer((n: number) => n + 1, 0);
  const seen = useRef<Set<string> | null>(null);
  seen.current ??= initiallySeen(msgs);
  const typingAt = typingIndex(msgs, seen.current);
  const shown = typingAt < 0 ? msgs : msgs.slice(0, typingAt + 1);
  const quiet = typingAt >= 0 || busy; // the reply controls wait until Area O1 has finished talking

  const back = view.nav?.back && (
    <Button size="sm" variant="ghost" className="px-2" disabled={busy} onClick={() => run(() => api.onboardingGoto(view.nav.back!.step, view.nav.back!.question))} aria-label="Back" title="Back">
      <ArrowLeft />
    </Button>
  );

  return (
    <section
      role="dialog"
      aria-modal
      aria-label={`Getting started with ${PRODUCT}`}
      className="fixed inset-0 z-50 flex animate-rise flex-col bg-surface md:inset-auto md:top-1/2 md:left-1/2 md:h-[min(88vh,860px)] md:w-[min(1080px,94vw)] md:-translate-x-1/2 md:-translate-y-1/2 md:border md:border-frame"
    >
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-frame px-4 lg:h-16">
        <img src="./favicon.svg" alt="" className="size-5" />
        <span className="display text-2xl uppercase">{PRODUCT}</span>
        <span className="hidden font-mono text-[10.5px] tracking-[0.08em] text-muted uppercase sm:inline">Getting started</span>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden sm:block">
            <Segmented label="Theme" size="sm" value={mode} onChange={setMode} options={THEMES} />
          </span>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("skip_all"))}>
            Skip setup
          </Button>
        </div>
      </header>
      <StepBar view={view} stepIndex={stepIndex} busy={busy} run={run} />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <details className="border-b border-line lg:hidden">
            <summary className="cursor-pointer px-5 py-2.5 font-mono text-[10.5px] tracking-[0.08em] text-ink-2 uppercase">
              Your profile so far · {view.panel.filter((l) => l.status !== "pending").length}
            </summary>
            <div className="max-h-[40vh] overflow-y-auto border-t border-line">
              <ProfilePanel view={view} />
            </div>
          </details>
          <Thread>
            {shown.map((m, i) => (
              <Message
                key={m.key}
                m={m}
                typing={i === typingAt}
                onTyped={() => {
                  seen.current!.add(m.key);
                  typed();
                }}
              >
                {m.widget === "linkedin" && step === "linkedin" && <LinkedInDrop busy={busy} run={run} />}
                {m.widget === "ai" && step === "ai" && (
                  <div className="mt-4 border border-line bg-paper p-4">
                    <ConnectAI busy={busy} onChoose={(choice) => run(() => api.onboardingAi(choice))} />
                  </div>
                )}
                {m.widget === "lookups" && (
                  <div className="mt-4 flex flex-col gap-2">
                    {view.state.lookups.map((l) => (
                      <LookupCard key={l.id} l={l} busy={busy} run={run} live={step === "lookups"} />
                    ))}
                  </div>
                )}
                {m.widget === "chats" && step === "chats" && <ChatsWidget busy={busy} run={run} />}
                {m.widget === "mail" && step === "mail" && (
                  <div className="mt-4 border border-line bg-paper p-4">
                    <GmailConnect busy={busy} onDone={() => run(() => api.onboardingStep("mail_done"))} />
                  </div>
                )}
              </Message>
            ))}
            {typingAt < 0 && busy && <Dots label={working || "Typing"} />}
          </Thread>

          <div className="border-t border-frame p-4" inert={quiet} aria-busy={quiet}>
            <div className={cx("flex items-start gap-2 transition-opacity duration-200", quiet && "opacity-40")}>
              {back}
              <div className="min-w-0 flex-1">
                <Composer view={view} busy={busy} run={run} />
              </div>
            </div>
            <p className="mt-2 truncate font-mono text-[10.5px] text-muted uppercase">
              Step {Math.min(stepIndex + 1, STEPS.length)} of {STEPS.length} · {STEPS[stepIndex]?.label} · Everything stays on this computer
            </p>
          </div>
        </div>
        <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-frame lg:block">
          <ProfilePanel view={view} />
        </aside>
      </div>
    </section>
  );
}

function StepBar({ view, stepIndex, busy, run }: { view: OnboardingView; stepIndex: number; busy: boolean; run: Run }) {
  return (
    <ol className="flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-line px-4 py-2.5" aria-label="Setup steps">
      {STEPS.map((s, i) => {
        const reachable = !!view.nav?.steps.find((x) => x.id === s.id)?.reachable && i !== stepIndex;
        const inner = (
          <>
            <span className={cx("h-1.5 w-6 border border-ink transition-colors duration-300", i < stepIndex ? "bg-ink" : i === stepIndex ? "bg-ink-2" : "bg-transparent")} />
            <span className={cx("font-mono text-[10.5px] tracking-[0.08em] whitespace-nowrap uppercase", i === stepIndex ? "text-ink" : "text-muted", i !== stepIndex && "hidden md:inline", reachable && "group-hover:text-ink")}>
              {s.label}
            </span>
          </>
        );
        return (
          <li key={s.id} aria-current={i === stepIndex ? "step" : undefined}>
            {reachable ? (
              <button type="button" className="group flex items-center gap-1.5" disabled={busy} onClick={() => run(() => api.onboardingGoto(s.id))} title={`Back to ${s.label}`}>
                {inner}
              </button>
            ) : (
              <span className="flex items-center gap-1.5">{inner}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** The scrolling thread. It follows the newest message while you're at the bottom, and leaves you alone when you've
 * scrolled up to read. */
function Thread({ children }: { children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const lastTop = useRef(0);
  useLayoutEffect(() => {
    const el = box.current;
    const content = inner.current;
    if (!el || !content) return;
    const follow = () => {
      if (stick.current) el.scrollTop = el.scrollHeight;
    };
    follow();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(follow);
    ro.observe(content);
    ro.observe(el); // the reply area growing (a fix form) shrinks the thread
    return () => ro.disconnect();
  }, []);
  return (
    <div
      ref={box}
      className="min-h-0 flex-1 overflow-y-auto px-5 py-6"
      onScroll={(e) => {
        // Only moving up lets go: following the thread only ever scrolls down, and content growing between our
        // scroll and its event mustn't read as the person scrolling away.
        const el = e.currentTarget;
        if (el.scrollTop < lastTop.current - 4) stick.current = false;
        if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) stick.current = true;
        lastTop.current = el.scrollTop;
      }}
    >
      <div ref={inner} className="mx-auto flex max-w-[720px] flex-col gap-6" aria-live="polite">
        {children}
      </div>
    </div>
  );
}

/** One message, styled like Ask's turns. Ours types in when it's new; its widget appears once it has. */
function Message({ m, typing, onTyped, children }: { m: Msg; typing: boolean; onTyped: () => void; children?: ReactNode }) {
  if (m.who === "you")
    return <div className="ml-10 animate-rise self-end bg-ink px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-on-ink">{m.text}</div>;
  return (
    <div className="animate-rise border-l border-ink pl-4" data-who="areao1">
      {typing ? (
        <Typed text={m.text} onDone={onTyped} />
      ) : (
        <>
          <p className="text-[15px] leading-relaxed">{m.text}</p>
          {m.quote && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-2">
              <FileText className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
              From your PDF: “{m.quote}”
            </p>
          )}
          {children}
        </>
      )}
    </div>
  );
}

function Typed({ text, onDone }: { text: string; onDone: () => void }) {
  const reduced = useReducedMotion();
  const [elapsed, setElapsed] = useState(-DOTS_MS);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (reduced) {
      done.current();
      return;
    }
    const t0 = performance.now();
    const total = typeDuration(text);
    let raf = 0;
    const tick = (now: number) => {
      const e = now - t0 - DOTS_MS;
      setElapsed(e);
      if (e >= total) done.current();
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, reduced]);
  if (elapsed < 0) return <Dots bare />;
  return (
    <p className="text-[15px] leading-relaxed">
      <span className="sr-only">{text}</span>
      <span aria-hidden>
        {typedPrefix(text, elapsed)}
        <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-tool-pulse bg-ink" />
      </span>
    </p>
  );
}

/** Area O1 is typing (or reading your PDF, or searching). */
function Dots({ label, bare }: { label?: string; bare?: boolean }) {
  const dots = (
    <span className="inline-flex items-center gap-1 py-1.5" role="status" aria-label={label || "Typing"}>
      {[0, 160, 320].map((d) => (
        <span key={d} className="size-1.5 animate-tool-pulse bg-ink" style={{ animationDelay: `${d}ms` }} />
      ))}
      {label && label !== "Typing" && <span className="ml-2 font-mono text-[10.5px] tracking-[0.08em] text-muted uppercase">{label}</span>}
    </span>
  );
  return bare ? dots : <div className="animate-rise border-l border-ink pl-4">{dots}</div>;
}

function LinkedInDrop({ busy, run }: { busy: boolean; run: Run }) {
  return (
    <div className="mt-4 [&>div]:mb-0 [&>div]:py-8">
      <DropZone busy={busy} accept="application/pdf" label="Upload your LinkedIn PDF" onFiles={(files) => files[0] && run(() => api.onboardingLinkedin(files[0]), "Reading your PDF")}>
        <Upload className="size-5" strokeWidth={1.5} aria-hidden />
        <p className="display text-2xl">Drop the PDF here, or click to choose</p>
        <p className="font-mono text-[11px] text-muted uppercase">Read on this computer · emails and phone numbers removed first</p>
      </DropZone>
    </div>
  );
}

function ChatsWidget({ busy, run }: { busy: boolean; run: Run }) {
  const toast = useToast();
  return (
    <div className="mt-4">
      <div className="mb-4 grid gap-px border border-line bg-line sm:grid-cols-2">
        <p className="bg-paper p-4 text-sm text-ink-2">
          <strong className="block font-medium text-ink">Claude</strong>
          Settings &gt; Privacy &gt; Export data, then drop the .zip (or its folder) from the email.
        </p>
        <p className="bg-paper p-4 text-sm text-ink-2">
          <strong className="block font-medium text-ink">ChatGPT</strong>
          Settings &gt; Data controls &gt; Export, then drop the .zip from the email.
        </p>
      </div>
      <ChatImport
        compact
        onDone={(summary) => {
          toast(summary);
          if (!busy) run(() => api.onboardingStep("chats_done"));
        }}
      />
    </div>
  );
}

/** Where Ask's message box sits: the reply for this step. */
function Composer({ view, busy, run }: { view: OnboardingView; busy: boolean; run: Run }) {
  const step = view.state.step;
  if (step === "linkedin") {
    const hasAnswers = view.panel.some((l) => l.status !== "pending");
    return (
      <div className="flex flex-wrap items-center justify-end gap-2">
        {hasAnswers ? (
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.onboardingGoto("questions"))}>
            Keep my answers and continue <ArrowRight />
          </Button>
        ) : (
          <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("skip_linkedin"))}>
            <SkipForward /> Skip, I don't have it handy
          </Button>
        )}
      </div>
    );
  }
  if (step === "questions")
    return view.question ? <Answer key={view.question.id} q={view.question} busy={busy} run={run} labels={labels(view)} /> : null;
  if (step === "ai")
    return (
      <div className="flex justify-end">
        <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingAi("skip"))}>
          <SkipForward /> Later, in Settings
        </Button>
      </div>
    );
  if (step === "lookups") {
    const open = view.state.lookups.some((l) => l.status === "offered");
    const searching = view.state.lookups.some((l) => l.status === "searching" || l.status === "accepted");
    return (
      <div className="flex justify-end">
        <Button variant={open ? "ghost" : "primary"} disabled={busy && open} onClick={() => run(() => api.onboardingStep("lookups_done"))}>
          {open ? "Not now, continue" : searching ? "Continue (searches finish in the background)" : "Continue"} <ArrowRight />
        </Button>
      </div>
    );
  }
  if (step === "chats")
    return (
      <div className="flex justify-end">
        <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("chats_skip"))}>
          <SkipForward /> Skip for now
        </Button>
      </div>
    );
  if (step === "mail")
    return (
      <div className="flex justify-end">
        <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("mail_skip"))}>
          <SkipForward /> Later, in Settings
        </Button>
      </div>
    );
  return null;
}

function asText(v: string | string[] | undefined) {
  return Array.isArray(v) ? v.join("; ") : (v ?? "");
}

/** Real titles for list items (a paper's arXiv link), known only after a lookup the person said Yes to. */
function labels(view: OnboardingView): Record<string, string> {
  return Object.assign({}, ...view.state.lookups.map((l) => l.resolved ?? {}));
}

/** The reply area under the conversation: Yes / No, let me fix it / Skip, a choice, or a month. */
function Answer({ q, busy, run, labels }: { q: OnboardingQuestion; busy: boolean; run: Run; labels: Record<string, string> }) {
  const [fixing, setFixing] = useState(false);
  const [lists, setLists] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(q.keys.filter((k) => Array.isArray(q.values[k])).map((k) => [k, q.values[k] as string[]])),
  );
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(q.keys.map((k) => [k, asText(q.values[k])])));
  const skip = (
    <Button type="button" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "skip"))}>
      Skip
    </Button>
  );
  let body: ReactNode;
  if (q.kind === "month")
    body = (
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.when) run(() => api.onboardingAnswer(q.id, "yes", draft.when));
        }}
      >
        <label className="min-w-0 flex-1 basis-48">
          <span className="label">Month</span>
          <input id="when" type="month" className="input" value={draft.when ?? ""} onChange={(e) => setDraft({ when: e.target.value })} />
        </label>
        <Button type="submit" variant="primary" disabled={busy || !draft.when}>
          <Check /> Save
        </Button>
        {skip}
      </form>
    );
  else if (q.kind === "choice")
    body = (
      <div className="flex flex-wrap gap-2">
        {q.options.map((o) => (
          <Button key={o.value} disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "yes", o.value))}>
            {o.label}
          </Button>
        ))}
        {skip}
      </div>
    );
  else if (fixing)
    body = (
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const all: Record<string, string | string[]> = { ...draft, ...lists };
          run(() => api.onboardingAnswer(q.id, "fix", q.keys.length === 1 ? all[q.keys[0]] : all));
        }}
      >
        {q.keys.map((k) =>
          Array.isArray(q.values[k]) ? (
            <div key={k}>
              <span className="label" id={`fix-${k}-label`}>
                {k}
              </span>
              <ChipInput id={`fix-${k}`} label={k} value={lists[k] ?? []} labels={labels} onChange={(items) => setLists({ ...lists, [k]: items })} />
              <span className="mt-1 block font-mono text-[10.5px] text-muted uppercase">; or Enter adds one · paste a list · Backspace removes the last · click one to edit</span>
            </div>
          ) : (
            <label key={k}>
              <span className="label">{k}</span>
              <input className="input" id={`fix-${k}`} autoFocus={k === q.keys[0]} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            </label>
          ),
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={busy}>
            <Check /> Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setFixing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  else
    body = (
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "yes"))}>
          <Check /> Yes
        </Button>
        <Button disabled={busy} onClick={() => setFixing(true)}>
          <Pencil /> No, let me fix it
        </Button>
        {skip}
      </div>
    );
  return body;
}

function ProfilePanel({ view }: { view: OnboardingView }) {
  const lines = view.panel.filter((l) => l.status !== "pending");
  return (
    <div aria-label="Your profile so far" role="region">
      <h2 className="eyebrow border-b border-line px-5 py-3 text-ink">Your profile so far</h2>
      {lines.length === 0 ? (
        <p className="px-5 py-8 text-sm text-ink-2">Each answer fills a line here. Skipped ones stay blank.</p>
      ) : (
        <dl>
          {lines.map((l) => (
            <div key={l.key} className="animate-rise border-b border-line px-5 py-3 last:border-b-0">
              <dt className="eyebrow">{l.label}</dt>
              <dd className={cx("mt-1 text-[15px] leading-snug", l.status === "skipped" ? "text-muted" : "text-ink")}>
                {l.status === "skipped" ? "Skipped" : Array.isArray(l.value) ? l.value.map((v) => labels(view)[v] ?? v).join("; ") : asText(l.value)}
                {l.status === "fixed" && <span className="ml-2 font-mono text-[10px] text-muted uppercase">edited</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

const LOOKUP_STATUS: Record<OnboardingLookup["status"], { label: string; tone: "ink" | "outline" | "muted" | "alert" }> = {
  offered: { label: "", tone: "muted" },
  declined: { label: "Skipped", tone: "muted" },
  searching: { label: "Searching", tone: "outline" },
  accepted: { label: "Searching", tone: "outline" },
  found: { label: "Found", tone: "ink" },
  done: { label: "Done", tone: "ink" },
  nothing_found: { label: "Nothing found", tone: "muted" },
  unreachable: { label: "Couldn't reach the site", tone: "alert" },
  blocked: { label: "Blocked by the site", tone: "alert" },
  failed: { label: "Didn't work", tone: "alert" },
};
const RETRYABLE = new Set(["nothing_found", "unreachable", "blocked", "failed"]);

function LookupCard({ l, busy, run, live }: { l: OnboardingLookup; busy: boolean; run: Run; live: boolean }) {
  const s = LOOKUP_STATUS[l.status];
  const searching = l.status === "searching" || l.status === "accepted";
  return (
    <div className="border border-line bg-paper p-4" data-lookup={l.id} data-status={l.status}>
      <div className="flex items-start gap-3">
        <Search className={cx("mt-1 size-5 shrink-0", searching && "animate-tool-pulse")} strokeWidth={1.5} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] leading-snug">{l.prompt}</p>
          <p className="mt-1 truncate font-mono text-[11px] text-muted">{l.targets.join(" · ")}</p>
          {s.label && (
            <p className="mt-3 flex flex-wrap items-center gap-2" role="status">
              <Chip tone={s.tone}>{s.label}</Chip>
              {l.result && <span className={cx("text-sm", s.tone === "alert" ? "text-alert" : "text-ink-2")}>{l.result}</span>}
            </p>
          )}
        </div>
      </div>
      {live && (l.status === "offered" || RETRYABLE.has(l.status)) && (
        <div className="mt-3 flex gap-2 pl-8">
          <Button variant={l.status === "offered" ? "primary" : "secondary"} disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, true), "Looking it up")}>
            {l.status === "offered" ? "Yes, look" : <><RotateCw /> Retry</>}
          </Button>
          {l.status === "offered" && (
            <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, false))}>
              No thanks
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
